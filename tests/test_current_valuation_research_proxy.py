from current_valuation_research_proxy import RELATIVE_MULTIPLES

def test_market_cap_and_ev_are_size_context_not_relative_value_multiples():
    assert "proxy_market_cap" not in RELATIVE_MULTIPLES
    assert "proxy_EV" not in RELATIVE_MULTIPLES
    assert {"proxy_P/E", "proxy_P/B", "proxy_P/S", "proxy_EV/Sales"} <= RELATIVE_MULTIPLES
