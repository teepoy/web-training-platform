from __future__ import annotations

from typing import Any


def select_torch_device(torch: Any) -> Any:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def select_ultralytics_device(torch: Any) -> int | str:
    if torch.cuda.is_available():
        return 0
    if torch.mps.is_available():
        return "mps"
    return "cpu"
