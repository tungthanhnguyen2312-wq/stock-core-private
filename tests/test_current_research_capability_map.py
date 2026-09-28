"""Focused classification and authority-boundary checks for the capability map."""

from tools.current_research_capability_map import decision_fitness


def test_decision_fitness_separates_current_multifactor_from_partial() -> None:
    assert decision_fitness(technical=True, fundamental=True, valuation=True, participation=True) == "CURRENT_RESEARCH_READY"
    assert decision_fitness(technical=True, fundamental=True, valuation=False, participation=True) == "PARTIAL_RESEARCH_READY"
    assert decision_fitness(technical=False, fundamental=True, valuation=True, participation=False) == "PARTIAL_RESEARCH_READY"


def test_technical_research_survives_missing_fundamental_and_valuation() -> None:
    assert decision_fitness(technical=True, fundamental=False, valuation=False, participation=True) == "TECHNICAL_RESEARCH_ONLY"
    assert decision_fitness(technical=False, fundamental=False, valuation=False, participation=False) == "INSUFFICIENT_CURRENT_EVIDENCE"
