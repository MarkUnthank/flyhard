import numpy as np
import torch
import pytest

from flyhard.connectome import SparseConnectome


def model():
    # 0 -> 1 (two synapses); 1 -> 2 (three synapses). No other edges.
    return SparseConnectome(np.array([0, 0, 1, 2]), np.array([0, 1]), np.array([2, 3]))


def test_edge_orientation_and_no_direct_bypass():
    net = model()
    x = torch.tensor([[1.0], [0.0], [0.0]])
    y = net(x)
    assert y[1, 0] > 0
    assert y[2, 0] == 0
    assert net(x, steps=2)[2, 0] > 0


def test_sparse_matches_dense_forward_and_edge_gradients():
    net = model()
    x = torch.tensor([[0.7], [-0.2], [0.3]])
    sparse = net(x)
    sparse.square().sum().backward()
    grad = net.edge_gain.grad.clone()
    net.zero_grad()
    dense = 0.5 * x + 0.5 * torch.tanh(net.matrix().to_dense() @ x)
    dense.square().sum().backward()
    torch.testing.assert_close(sparse, dense)
    torch.testing.assert_close(grad, net.edge_gain.grad)
    assert torch.all(grad != 0)


def test_training_cannot_create_an_edge():
    net = model()
    before = (net.crow.clone(), net.col.clone())
    opt = torch.optim.Adam(net.parameters(), lr=0.01)
    loss = net(torch.ones(3, 1), steps=3).square().mean()
    loss.backward()
    assert torch.isfinite(net.edge_gain.grad).all()
    assert torch.isfinite(net.leak.grad).all()
    opt.step()
    assert torch.equal(net.crow, before[0]) and torch.equal(net.col, before[1])
    assert net.matrix()._nnz() == 2


@pytest.mark.parametrize('device', ['cpu'] + (['cuda'] if torch.cuda.is_available() else []))
def test_recurrent_sparse_gradient_matches_dense_reference(device):
    net = model().to(device)
    x = torch.tensor([[0.7], [-0.2], [0.3]], device=device, requires_grad=True)
    y = net(x, steps=4)
    y.square().sum().backward()
    sparse_grads = (net.edge_gain.grad.clone(), net.leak.grad.clone(), x.grad.clone())
    net.zero_grad(); x.grad = None
    dense = x
    w = net.matrix().to_dense()
    leak = (0.05 + 0.90 * torch.sigmoid(net.leak))[:,None]
    for _ in range(4):
        dense = (1-leak)*dense + leak*torch.tanh(w @ dense)
    dense.square().sum().backward()
    torch.testing.assert_close(y, dense)
    for a,b in zip(sparse_grads, [net.edge_gain.grad, net.leak.grad, x.grad]):
        torch.testing.assert_close(a,b)


def test_sparse_derivative_by_finite_differences():
    from flyhard.connectome import _EdgeSparseMM
    net = model().double()
    values = net.base.clone().requires_grad_(True)
    x = torch.tensor([[0.3,-0.2], [-0.4,0.6], [0.9,0.1]], dtype=torch.double, requires_grad=True)
    assert torch.autograd.gradcheck(lambda v,s: _EdgeSparseMM.apply(v, net.crow, net.col, net.rows, s), (values,x))
