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
