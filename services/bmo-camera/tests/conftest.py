from pathlib import Path
import sys

import pytest


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.value = start

    def now(self) -> float:
        return self.value

    def set(self, value: float) -> None:
        self.value = value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def clock():
    return FakeClock()
