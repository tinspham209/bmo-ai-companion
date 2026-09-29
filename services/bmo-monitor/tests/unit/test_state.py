import math

import pytest

from state import select_emotion


@pytest.mark.parametrize(
    ("cpu", "temperature", "disk", "expected"),
    [
        (80.0, 70.0, 500_000_000, "happy"),
        (80.01, 70.0, 500_000_000, "stressed"),
        (80.0, 70.01, 500_000_000, "hot"),
        (80.0, 70.0, 499_999_999, "worried"),
        (95.0, 71.0, 100, "hot"),
        (95.0, 70.0, 100, "stressed"),
        (80.0, 71.0, 100, "hot"),
    ],
)
def test_emotion_thresholds_and_precedence(cpu, temperature, disk, expected):
    assert select_emotion(cpu, temperature, disk) == expected


@pytest.mark.parametrize(
    ("cpu", "temperature", "disk"),
    [
        (None, 60.0, 1_000_000_000),
        (10.0, None, 1_000_000_000),
        (10.0, 60.0, None),
        (math.nan, 60.0, 1_000_000_000),
        (10.0, math.inf, 1_000_000_000),
        (True, 60.0, 1_000_000_000),
        (10.0, 60.0, True),
        (-1.0, 60.0, 1_000_000_000),
        (10.0, -1.0, 1_000_000_000),
    ],
)
def test_incomplete_or_invalid_emotion_inputs_are_unavailable(cpu, temperature, disk):
    assert select_emotion(cpu, temperature, disk) is None


def test_all_collected_nominal_metrics_do_not_alter_specified_mapping():
    assert select_emotion(20.0, 55.0, 1_000_000_000) == "happy"
