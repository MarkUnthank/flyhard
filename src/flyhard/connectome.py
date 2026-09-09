"""Sparse recurrent rate model with immutable measured adjacency.

Each measured edge has a trainable bounded gain, and every neuron has a
trainable leak rate. E01 uses unsigned transmission as a numerical test;
transmitter/receptor biology is not asserted by this model.
"""
import torch
from torch import nn


class SparseConnectome(nn.Module):
    def __init__(self, crow, col, counts, *, edge_init=0.0, leak_init=0.0):
        super().__init__()
        self.n = len(crow) - 1
        self.register_buffer("crow", torch.as_tensor(crow, dtype=torch.int64))
        self.register_buffer("col", torch.as_tensor(col, dtype=torch.int64))
        counts = torch.as_tensor(counts, dtype=torch.float32)
        rows = torch.repeat_interleave(torch.arange(self.n), torch.diff(self.crow))
        totals = torch.zeros(self.n).index_add_(0, rows, counts)
        self.register_buffer("base", counts / totals[rows].clamp_min(1))
        self.edge_gain = nn.Parameter(torch.full_like(counts, float(edge_init)))
        self.leak = nn.Parameter(torch.full((self.n,), float(leak_init)))

    def edge_values(self):
        return self.base * (0.05 + 0.90 * torch.sigmoid(self.edge_gain))

    def matrix(self, values=None):
        if values is None:
            values = self.edge_values()
        return torch.sparse_csr_tensor(self.crow, self.col, values, size=(self.n, self.n), check_invariants=False)

    def forward(self, state, steps=1, drive=None):
        """State shape [neurons, batch]; row=postsynaptic, col=presynaptic.

        An optional external drive must already be mapped to declared input
        neurons by the experiment. There is no direct input-to-output bypass.
        """
        values = self.edge_values()
        leak = (0.05 + 0.90 * torch.sigmoid(self.leak))[:, None]
        for _ in range(steps):
            # Each step has its own sparse wrapper. Gradients accumulate on the
            # dense edge values, avoiding unsupported sparse CSR addition on macOS.
            matrix = self.matrix(values)
            signal = torch.sparse.mm(matrix, state)
            if drive is not None:
                signal = signal + drive
            state = (1 - leak) * state + leak * torch.tanh(signal)
        return state
