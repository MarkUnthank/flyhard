"""Goal-conditioned full measured connectome; frozen sensory and motor maps."""
import numpy as np
import torch
from torch import nn
from flyhard.connectome import SparseConnectome
from flyhard.parking import encode


class ParkingPolicy(nn.Module):
    def __init__(self,graph,sensory_ids,motor_ids,seed=420):
        super().__init__();rng=np.random.default_rng(seed)
        self.core=SparseConnectome(graph['crow'],graph['col'],graph['counts'])
        self.register_buffer('sensory_ids',torch.as_tensor(sensory_ids,dtype=torch.long))
        self.register_buffer('motor_ids',torch.as_tensor(motor_ids,dtype=torch.long))
        count=encode(np.zeros((1,11),np.float32)).shape[1]
        self.register_buffer('feature_ids',torch.tensor(rng.integers(0,count,len(sensory_ids))))
        self.register_buffer('input_signs',torch.tensor(rng.choice([-1.,1.],len(sensory_ids)),dtype=torch.float32))
        self.register_buffer('decoder',torch.tensor(rng.normal(size=(5,len(motor_ids)))/np.sqrt(len(motor_ids)),dtype=torch.float32))
        self.register_buffer('scale',torch.tensor([.35,1.2]))

    def raw(self,features):
        drive=torch.zeros(self.core.n,len(features),device=features.device)
        drive[self.sensory_ids]=features[:,self.feature_ids].T*self.input_signs[:,None]
        state=self.core(torch.zeros_like(drive),steps=4,drive=drive)
        return state[self.motor_ids].T@self.decoder.T,state

    def training_outputs(self,features):
        raw,_=self.raw(features)
        return .35*torch.tanh(raw[:,0]),1.2*torch.sigmoid(raw[:,1]),raw[:,2:]

    def forward(self,features,return_state=False):
        raw,state=self.raw(features)
        # A discrete learned gear choice can cross a direction-change cusp
        # without creating a stationary fixed point at the average of +/- speed.
        direction=raw[:,2:].argmax(dim=1)-1
        output=torch.stack([.35*torch.tanh(raw[:,0]),1.2*torch.sigmoid(raw[:,1])*direction],dim=1)
        return (output,state) if return_state else output

    def calibrate(self,features):
        with torch.no_grad():
            raw,state=self.raw(features)
            self.decoder.mul_((.3/raw.std(dim=0).clamp_min(1e-5))[:,None])
            self.decoder[2:].mul_(5.)

    def checkpoint_state(self):
        return {k:v.detach().cpu() for k,v in self.state_dict().items()
                if k not in {'core.crow','core.col','core.rows','core.base'}}
