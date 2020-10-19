import numpy as np
from typing import Callable


class NumpyBackend:
    def __init__(self, share_std: float=5):
        self.share_std = share_std

    def get_product_triple(self, shape_0: list, shape_1: list, func: Callable[[np.ndarray, np.ndarray], np.ndarray]):
        u0 = np.random.normal(0, self.share_std, shape_0)
        v0 = np.random.normal(0, self.share_std, shape_1) # std = 5
        u1 = np.random.normal(0, self.share_std, shape_0)
        v1 = np.random.normal(0, self.share_std, shape_1)
        w = func(u0 + u1, v0 + v1)  # std ≈ 10 * 10
        w0 = np.random.normal(0, self.share_std ** 2, w.shape)
        w1 = w - w0
        return (u0, v0, w0), (u1, v1, w1)