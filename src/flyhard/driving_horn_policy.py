"""One connectome core commands both forelegs; no direct control bypass."""
import numpy as np
import torch
from torch import nn
from flyhard.connectome import SparseConnectome
from flyhard.driving_horn import FIELDS, HISTORY, encode


class DrivingHornPolicy(nn.Module):
    def __init__(self, graph, sensory_ids, motor_ids, neutral, action_scale, seed=802):
        super().__init__()
        self.core = SparseConnectome(graph['crow'], graph['col'], graph['counts'])
        rng = np.random.default_rng(seed)
        count = len(encode(np.zeros((HISTORY, len(FIELDS)))))
        self.register_buffer('sensory_ids', torch.as_tensor(sensory_ids, dtype=torch.long))
        self.register_buffer('motor_ids', torch.as_tensor(motor_ids, dtype=torch.long))
        self.register_buffer('feature_ids', torch.tensor(rng.integers(0, count, len(sensory_ids))))
        self.register_buffer('input_signs', torch.tensor(rng.choice([-1., 1.], len(sensory_ids)), dtype=torch.float32))
        self.register_buffer('decoder', torch.tensor(rng.normal(size=(14, len(motor_ids)))/np.sqrt(len(motor_ids)), dtype=torch.float32))
        self.register_buffer('neutral', torch.as_tensor(neutral, dtype=torch.float32))
        self.register_buffer('action_scale', torch.as_tensor(action_scale, dtype=torch.float32))

    def forward(self, features, return_state=False):
        drive = torch.zeros(self.core.n, len(features), device=features.device)
        drive[self.sensory_ids] = features[:, self.feature_ids].T*self.input_signs[:, None]
        state = self.core(torch.zeros_like(drive), steps=4, drive=drive)
        actions = self.neutral+self.action_scale*torch.tanh(state[self.motor_ids].T@self.decoder.T)
        return (actions, state) if return_state else actions

    def calibrate(self, features):
        with torch.no_grad():
            _, state = self(features, return_state=True)
            raw = state[self.motor_ids].T@self.decoder.T
            self.decoder.mul_((.2/raw.std(dim=0).clamp_min(1e-5))[:, None])

    def checkpoint_state(self):
        return {k:v.detach().cpu() for k,v in self.state_dict().items()
                if k not in {'core.crow', 'core.col', 'core.rows', 'core.base'}}
