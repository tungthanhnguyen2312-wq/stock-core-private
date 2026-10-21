"""Five-name readiness uses retained method status. It does not invent a target."""
import stocklookup_core.decision.investment_decision_workspace_projection as workspace


SESSION = "2026-10-20"


def _view(methods):
    return workspace._valuation_view({
        "valuation": {
            "applicable_methods": methods,
            "absolute_research_context": {},
            "peer_relative_context": {"methods": {}},
        },
    })


def test_five_names_keep_proxy_blocked_and_not_applicable_apart():
    cases = {
        "HPG": {
            "P/B_CURRENT_RESEARCH": {
                "status": "RESEARCH_USABLE", "value": 1.0,
                "limitations": ["CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE"],
                "period_basis": "CURRENT_RESEARCH", "blocker_reason_codes": [],
            },
            "P/E_TTM": {"status": "INPUT_BLOCKED", "value": None, "blocker_reason_codes": ["TTM_INPUT_UNAVAILABLE"]},
            "EV/EBITDA": {"status": "INPUT_BLOCKED", "value": None, "blocker_reason_codes": ["EXACT_EBITDA_COMPARABILITY_NOT_RETAINED"]},
        },
        "SSI": {
            "EV/EBITDA": {"status": "NOT_APPLICABLE", "value": None, "blocker_reason_codes": ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]},
            "P/B": {"status": "INPUT_BLOCKED", "value": None, "blocker_reason_codes": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"]},
        },
        "EVF": {
            "P/B": {"status": "NOT_APPLICABLE", "value": None, "blocker_reason_codes": ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]},
            "P/E": {"status": "INPUT_BLOCKED", "value": None, "blocker_reason_codes": ["PLANNED_OR_UNEXECUTED_ACTION_IS_NOT_SHARES_OUTSTANDING"]},
        },
        "PAN": {
            "P/B_CURRENT_RESEARCH": {
                "status": "RESEARCH_USABLE", "value": 1.0,
                "limitations": ["CURRENT_RESEARCH_ONLY"], "blocker_reason_codes": [],
            },
        },
        "PNJ": {
            "P/B": {"status": "INPUT_BLOCKED", "value": None, "blocker_reason_codes": ["OFFICIAL_QUALIFIED_FINANCIAL_INPUT_UNAVAILABLE"]},
            "P/E_REPORTED_PERIOD": {
                "status": "RESEARCH_USABLE", "value": 1.0,
                "limitations": ["NOT_PIT"], "blocker_reason_codes": [],
            },
        },
    }
    expected = {
        "HPG": {"P/B_CURRENT_RESEARCH": "RESEARCH_PROXY", "P/E_TTM": "BLOCKED", "EV/EBITDA": "BLOCKED"},
        "SSI": {"EV/EBITDA": "NOT_APPLICABLE", "P/B": "BLOCKED"},
        "EVF": {"P/B": "NOT_APPLICABLE", "P/E": "BLOCKED"},
        "PAN": {"P/B_CURRENT_RESEARCH": "RESEARCH_PROXY"},
        "PNJ": {"P/B": "BLOCKED", "P/E_REPORTED_PERIOD": "RESEARCH_PROXY"},
    }
    for ticker, methods in cases.items():
        view = _view(methods)
        readiness = view["research_readiness"]
        for method_id, label in expected[ticker].items():
            assert readiness["methods"][method_id]["readiness"] == label
        assert readiness["normalized_earnings"]["readiness"] == "BLOCKED"
        assert readiness["normalized_earnings"]["reason_code"] == "NORMALIZED_EARNINGS_CONTRACT_NOT_ADMITTED"
        assert readiness["intrinsic_value"]["reason_code"] == "INTRINSIC_VALUE_METHOD_NOT_ADMITTED"
        assert readiness["probability_status"] == "NOT_EMITTED"
        assert readiness["official_target_price_status"] == "NOT_EMITTED"
        assert "target_price" not in view
    assert _view(cases["SSI"])["research_readiness"]["share_or_corporate_action_blockers"] == [
        "CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION",
    ]
    assert _view(cases["EVF"])["research_readiness"]["share_or_corporate_action_blockers"] == [
        "PLANNED_OR_UNEXECUTED_ACTION_IS_NOT_SHARES_OUTSTANDING",
    ]


def test_conditional_cases_drop_a_target_and_keep_bear_base_bull():
    clean = workspace.conditional_scenario_view({
        "bear_case": {"case_status": "CONDITIONAL", "reason_code": "NO_QUALIFIED_INVALIDATION_OR_ADVERSE_EVIDENCE", "is_actionable": False},
        "base_case": {"case_status": "OBSERVED_REFERENCE", "reason_code": "CONTINUATION", "is_actionable": False},
        "bull_case": {"case_status": "NOT_ADMITTED", "reason_code": "NO_QUALIFIED_ENTRY_TRIGGER", "is_actionable": False},
        "limitations": ["RESEARCH_ONLY_NOT_EXECUTION"],
    })
    assert [clean[name]["case_status"] for name in ("bear", "base", "bull")] == [
        "CONDITIONAL", "OBSERVED_REFERENCE", "NOT_ADMITTED",
    ]
    assert clean["probability_status"] == "NOT_EMITTED"
    assert clean["official_target_price_status"] == "NOT_EMITTED"
    poisoned = workspace.conditional_scenario_view({
        "bull_case": {"case_status": "CONDITIONAL", "target_price": 99, "is_actionable": False},
    })
    assert poisoned["bull"]["case_status"] == "BLOCKED"
    assert poisoned["bull"]["reason_code"] == "CASE_MISSING_OR_TARGET_NOT_ADMITTED"
    rejected = workspace._accepted_scenario_binding({
        "contract_version": "current_evidence_bound_scenario_integrated_binding/v1",
        "session": "2026-10-21",
        "probability_status": "UNKNOWN_UNCALIBRATED",
        "is_actionable": False,
        "records": {},
    }, SESSION)
    assert rejected is None
