"""Three-point-turn outputs learned inside the full measured connectome."""
import numpy as np
import torch
from flyhard.parking_policy import ParkingPolicy
from flyhard.three_point import encode

class ThreePointPolicy(ParkingPolicy):
    def __init__(self,graph,sensory_ids,motor_ids,seed=521):
        super().__init__(graph,sensory_ids,motor_ids,seed)
        rng=np.random.default_rng(seed)
        count=encode(np.zeros((1,11),np.float32)).shape[1]
        self.feature_ids=torch.as_tensor(rng.integers(0,count,len(sensory_ids)),dtype=torch.long)

    def training_outputs(self,features):
        raw,_=self.raw(features)
        return self.scale[0]*torch.tanh(raw[:,0]),self.scale[1]*torch.sigmoid(raw[:,1]),raw[:,2:]

    def forward(self,features,return_state=False):
        raw,state=self.raw(features)
        direction=raw[:,2:].argmax(dim=1)-1
        output=torch.stack([self.scale[0]*torch.tanh(raw[:,0]),self.scale[1]*torch.sigmoid(raw[:,1])*direction],dim=1)
        return (output,state) if return_state else output
