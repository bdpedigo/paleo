from typing import Union

import numpy as np

type Number = Union[int, float, np.number]
type Integer = Union[int, np.integer]
type Graph = Union[np.ndarray, tuple[np.ndarray, np.ndarray]]
