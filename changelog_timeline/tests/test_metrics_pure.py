"""Testes unitarios das funcoes puras compartilhadas (metrics/)."""
import random

from metrics.constants import (
    ACTIVE_STATES, WIP_ACTIVE_STATES, is_backward_transition,
)
from metrics.forecast_core import MAX_WEEKS, percentile_from_sorted, simulate_completion_weeks
from metrics.timeutils import week_to_date_range


def test_week_to_date_range_iso():
    assert week_to_date_range("2026-W32") == "03/08 - 09/08"
    assert week_to_date_range("2026-W01") == "29/12 - 04/01"


def test_week_to_date_range_invalid_returns_input():
    assert week_to_date_range("lixo") == "lixo"
    assert week_to_date_range("2026-Wxx") == "2026-Wxx"


def test_percentile_from_sorted():
    data = list(range(1, 101))
    assert percentile_from_sorted(data, 50) == 50
    assert percentile_from_sorted(data, 85) == 85
    assert percentile_from_sorted(data, 100) == 100
    assert percentile_from_sorted([], 50) == 0


def test_simulation_is_deterministic_with_seed_and_sorted():
    random.seed(42)
    a = simulate_completion_weeks([2, 3, 1, 4], remaining_items=10, simulations=200)
    random.seed(42)
    b = simulate_completion_weeks([2, 3, 1, 4], remaining_items=10, simulations=200)
    assert a == b
    assert a == sorted(a) and len(a) == 200


def test_simulation_respects_max_weeks():
    res = simulate_completion_weeks([0], remaining_items=5, simulations=10)
    assert set(res) == {MAX_WEEKS}


def test_simulation_constant_throughput():
    assert set(simulate_completion_weeks([5], remaining_items=10, simulations=20)) == {2}


def test_backward_transition():
    assert is_backward_transition("Test", "In Progress") is True
    assert is_backward_transition("In Progress", "Test") is False
    assert is_backward_transition(None, "Done") is False
    assert is_backward_transition("Done", "Done") is False


def test_active_states_contract():
    assert ACTIVE_STATES == {"In Progress", "Blocked", "Test", "Waiting for Delivery"}
    assert WIP_ACTIVE_STATES == {"In Progress", "Test"}
