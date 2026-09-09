"""Engineered, frozen sensory/motor interfaces around the trainable connectome."""
import numpy as np
import torch
from torch import nn
from flyhard.connectome import SparseConnectome


class WheelPolicy(nn.Module):
    def __init__(self, graph, sensory_ids, motor_ids, neutral, action_scale, seed=123):
        super().__init__()
        self.core = SparseConnectome(graph['crow'],graph['col'],graph['counts'])
        rng=np.random.default_rng(seed)
        self.register_buffer('sensory_ids',torch.as_tensor(sensory_ids,dtype=torch.long))
        self.register_buffer('motor_ids',torch.as_tensor(motor_ids,dtype=torch.long))
        self.register_buffer('feature_ids',torch.tensor(rng.integers(0,10,len(sensory_ids))))
        self.register_buffer('input_signs',torch.tensor(rng.choice([-1.,1.],len(sensory_ids)),dtype=torch.float32))
        self.register_buffer('decoder',torch.tensor(rng.normal(size=(7,len(motor_ids)))/np.sqrt(len(motor_ids)),dtype=torch.float32))
        self.register_buffer('neutral',torch.tensor(neutral,dtype=torch.float32))
        self.register_buffer('action_scale',torch.tensor(action_scale,dtype=torch.float32))

    def neural_state(self, observations):
        # Observation: requested angle, measured angle, seven measured joint angles.
        target=observations[:,0]/0.5
        features=torch.cat([target[:,None],target.square()[:,None],observations[:,1:2]/0.5,
                            (observations[:,2:]-self.neutral)/self.action_scale],dim=1).clamp(-2,2)
        drive=torch.zeros(self.core.n,len(observations),device=observations.device)
        drive[self.sensory_ids]=features[:,self.feature_ids].T*self.input_signs[:,None]
        # Four graph updates per 50 ms control decision. State reset is explicit
        # for this memoryless stationary skill; no biological time-constant claim.
        return self.core(torch.zeros_like(drive),steps=4,drive=drive)

    def forward(self,observations,return_state=False):
        state=self.neural_state(observations)
        actions=self.neutral+self.action_scale*torch.tanh(state[self.motor_ids].T@self.decoder.T)
        return (actions,state) if return_state else actions

    def calibrate_frozen_decoder(self,observations):
        # Scale each fixed random projection to a small initial signal. No target
        # actions or fitting are involved, and the decoder remains untrainable.
        with torch.no_grad():
            state=self.neural_state(observations)
            raw=state[self.motor_ids].T@self.decoder.T
            self.decoder.mul_((0.15/raw.std(dim=0).clamp_min(1e-5))[:,None])
