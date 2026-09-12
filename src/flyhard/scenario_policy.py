"""Pedal demands learned inside the full measured connectome, for any scenario.

Identical in structure to the crossing policy: two sigmoid heads on a random readout
of the motor population, with only the core's edge gains and leaks trainable. The
scenario supplies its own encoder, so one architecture serves several behaviours
without any of them getting a bespoke decoder.
"""
import numpy as np
import torch

from flyhard.connectome import SparseConnectome


class PedalPolicy(torch.nn.Module):
    def __init__(self, graph, sensory_ids, motor_ids, feature_count, seed=733):
        super().__init__()
        rng = np.random.default_rng(seed)
        self.core = SparseConnectome(graph['crow'], graph['col'], graph['counts'])
        self.register_buffer('sensory_ids', torch.as_tensor(sensory_ids, dtype=torch.long))
        self.register_buffer('motor_ids', torch.as_tensor(motor_ids, dtype=torch.long))
        self.register_buffer('feature_ids', torch.as_tensor(
            rng.integers(0, feature_count, len(sensory_ids)), dtype=torch.long))
        self.register_buffer('input_signs', torch.tensor(
            rng.choice([-1., 1.], len(sensory_ids)), dtype=torch.float32))
        self.register_buffer('decoder', torch.tensor(
            rng.normal(size=(2, len(motor_ids)))/np.sqrt(len(motor_ids)), dtype=torch.float32))

    def raw(self, features):
        drive = torch.zeros(self.core.n, len(features), device=features.device)
        drive[self.sensory_ids] = features[:, self.feature_ids].T*self.input_signs[:, None]
        state = self.core(torch.zeros_like(drive), steps=4, drive=drive)
        return state[self.motor_ids].T@self.decoder.T, state

    def training_outputs(self, features):
        raw, _ = self.raw(features)
        return torch.sigmoid(raw[:, 0]), torch.sigmoid(raw[:, 1])

    def forward(self, features, return_state=False):
        raw, state = self.raw(features)
        output = torch.stack([torch.sigmoid(raw[:, 0]), torch.sigmoid(raw[:, 1])], dim=1)
        return (output, state) if return_state else output

    def calibrate(self, features):
        with torch.no_grad():
            raw, _ = self.raw(features)
            self.decoder.mul_((.3/raw.std(dim=0).clamp_min(1e-5))[:, None])

    def checkpoint_state(self):
        return {k: v.detach().cpu() for k, v in self.state_dict().items()
                if k not in {'core.crow', 'core.col', 'core.rows', 'core.base'}}
