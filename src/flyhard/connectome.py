"""Sparse recurrent rate model with immutable measured adjacency.

Each measured edge has a trainable bounded gain, and every neuron has a
trainable leak rate. E01 uses unsigned transmission as a numerical test;
transmitter/receptor biology is not asserted by this model.
"""
import torch
from torch import nn


class _EdgeSparseMM(torch.autograd.Function):
    """First-order SpMM derivative evaluated only at measured edges.

    PyTorch 2.8's CSR-value backward allocated a dense N-by-N intermediate
    on the full graph (101.57 GiB). The exact derivative at an edge i<-j is
    dot(dL/dY[i], X[j]). Chunked indexing bounds temporary memory; the state
    derivative remains an ordinary PyTorch sparse matrix multiplication.
    """
    @staticmethod
    def forward(ctx, values, crow, col, rows, state):
        n = len(crow)-1
        matrix = torch.sparse_csr_tensor(crow, col, values, size=(n,n), check_invariants=False)
        ctx.save_for_backward(values, crow, col, rows, state)
        return torch.sparse.mm(matrix, state)

    @staticmethod
    def backward(ctx, output_grad):
        values, crow, col, rows, state = ctx.saved_tensors
        value_grad = torch.empty_like(values) if ctx.needs_input_grad[0] else None
        if value_grad is not None:
            for start in range(0, len(values), 262144):
                end = min(start+262144, len(values))
                value_grad[start:end] = (
                    output_grad[rows[start:end]] * state[col[start:end]]
                ).sum(dim=1)
        state_grad = None
        if ctx.needs_input_grad[4]:
            n = len(crow)-1
            matrix = torch.sparse_csr_tensor(crow, col, values, size=(n,n), check_invariants=False)
            state_grad = torch.sparse.mm(matrix.transpose(0,1), output_grad)
        return value_grad, None, None, None, state_grad


class SparseConnectome(nn.Module):
    def __init__(self, crow, col, counts, *, edge_init=0.0, leak_init=0.0):
        super().__init__()
        self.n = len(crow) - 1
        self.register_buffer("crow", torch.as_tensor(crow, dtype=torch.int64))
        self.register_buffer("col", torch.as_tensor(col, dtype=torch.int64))
        counts = torch.as_tensor(counts, dtype=torch.float32)
        rows = torch.repeat_interleave(torch.arange(self.n), torch.diff(self.crow))
        self.register_buffer("rows", rows)
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
            signal = _EdgeSparseMM.apply(values, self.crow, self.col, self.rows, state)
            if drive is not None:
                signal = signal + drive
            state = (1 - leak) * state + leak * torch.tanh(signal)
        return state
