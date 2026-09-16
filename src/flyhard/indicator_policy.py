"""Connectome indicator policy with frozen GPS/navigation/traffic encoding.

This pilot uses measured navigation coordinates, not visual perception. No
episode time, route-progress index, expected signal or requested stalk angle is
an input. The only learned parameters are the measured graph's gains and leaks.
"""
import numpy as np
import torch
from torch import nn

from flyhard.connectome import SparseConnectome


CONTEXT_FIELDS = ["ego_x", "ego_y", "yaw_rad", "vx", "vy", "speed",
                  "goal_x", "goal_y", "near_dx", "near_dy", "near_dvx",
                  "near_dvy", "nearby_count"]
CENTRE = np.array([-0.5, 0.0], dtype=np.float32)


def encode_context(context, wheel_request=0.):
    """Fixed spatial population code in the coordinate frame of the destination.

    Spatial Gaussian features are a generic engineered navigation encoder, not
    a claimed biological sensory mapping. Their centres do not use signal labels.
    """
    x = np.asarray(context, dtype=np.float32)
    single = x.ndim == 1
    x = np.atleast_2d(x)
    if x.shape[1] != len(CONTEXT_FIELDS) or not np.isfinite(x).all():
        raise ValueError("Expected finite navigation/traffic observations")
    g = x[:, 6:8] - CENTRE
    g = g / np.linalg.norm(g, axis=1, keepdims=True).clip(1e-6)
    tangent = np.stack([-g[:, 1], g[:, 0]], axis=1)
    position = (x[:, :2] - CENTRE) / 40.0
    along = (position * g).sum(axis=1)
    across = (position * tangent).sum(axis=1)
    heading = np.stack([np.cos(x[:, 2]), np.sin(x[:, 2])], axis=1)
    head_a, head_b = (heading * g).sum(axis=1), (heading * tangent).sum(axis=1)
    coordinates = np.linspace(-1.6, 1.6, 11, dtype=np.float32)
    grid = np.stack(np.meshgrid(coordinates, coordinates), axis=-1).reshape(-1, 2)
    delta = np.stack([along, across], axis=1)[:, None, :] - grid[None]
    place = np.exp(-np.square(delta).sum(axis=2) / (2 * 0.24 ** 2))
    raw = np.stack([np.ones(len(x)), along, across, head_a, head_b,
                    (x[:, 3:5] * g).sum(axis=1) / 10,
                    (x[:, 3:5] * tangent).sum(axis=1) / 10, x[:, 5] / 10,
                    (x[:, 8:10] * g).sum(axis=1) / 40,
                    (x[:, 8:10] * tangent).sum(axis=1) / 40,
                    (x[:, 10:12] * g).sum(axis=1) / 10,
                    (x[:, 10:12] * tangent).sum(axis=1) / 10, x[:, 12] / 16], axis=1)
    wheel = np.broadcast_to(np.asarray(wheel_request, dtype=np.float32), (len(x),)) / .45
    wheel_features = np.stack([wheel, wheel ** 2, wheel ** 3], axis=1)
    result = np.concatenate([raw.clip(-2, 2), place, place * head_a[:, None],
                             place * head_b[:, None], wheel_features], axis=1).astype(np.float32)
    return result[0] if single else result


class IndicatorPolicy(nn.Module):
    def __init__(self, graph, sensory_ids, motor_ids, neutral, action_scale, seed=123):
        super().__init__()
        self.core = SparseConnectome(graph["crow"], graph["col"], graph["counts"])
        rng = np.random.default_rng(seed)
        n_features = len(encode_context(np.array([0, 0, 0, 0, 0, 0, 60, 0, 0, 0, 0, 0, 0])))
        self.register_buffer("sensory_ids", torch.as_tensor(sensory_ids, dtype=torch.long))
        self.register_buffer("motor_ids", torch.as_tensor(motor_ids, dtype=torch.long))
        feature_ids = rng.integers(0, n_features - 3, len(sensory_ids))
        # A fixed quarter of the sensory interface carries wheel instructions.
        # The remaining population encodes navigation/traffic, with no signal cue.
        feature_ids[:len(sensory_ids) // 4] = rng.integers(n_features - 3, n_features, len(sensory_ids) // 4)
        rng.shuffle(feature_ids)
        self.register_buffer("feature_ids", torch.tensor(feature_ids))
        self.register_buffer("input_signs", torch.tensor(rng.choice([-1., 1.], len(sensory_ids)), dtype=torch.float32))
        self.register_buffer("decoder", torch.tensor(rng.normal(size=(len(neutral), len(motor_ids))) /
                                                      np.sqrt(len(motor_ids)), dtype=torch.float32))
        self.register_buffer("neutral", torch.as_tensor(neutral, dtype=torch.float32))
        self.register_buffer("action_scale", torch.as_tensor(action_scale, dtype=torch.float32))

    def forward(self, features, return_state=False):
        drive = torch.zeros(self.core.n, len(features), device=features.device)
        drive[self.sensory_ids] = features[:, self.feature_ids].T * self.input_signs[:, None]
        state = self.core(torch.zeros_like(drive), steps=4, drive=drive)
        actions = self.neutral + self.action_scale * torch.tanh(state[self.motor_ids].T @ self.decoder.T)
        return (actions, state) if return_state else actions

    def calibrate(self, features):
        with torch.no_grad():
            _, state = self(features, return_state=True)
            raw = state[self.motor_ids].T @ self.decoder.T
            self.decoder.mul_((0.20 / raw.std(dim=0).clamp_min(1e-5))[:, None])

    def checkpoint_state(self):
        # Immutable graph buffers are restored from the separately hashed graph.
        return {k: v.detach().cpu() for k, v in self.state_dict().items()
                if k not in {"core.crow", "core.col", "core.rows", "core.base"}}
