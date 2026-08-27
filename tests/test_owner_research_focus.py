from owner_research_focus import broader_watchlist, load_owner_research_focus, owner_focus_tickers


def test_owner_focus_config_is_portable_and_not_holdings():
    config = load_owner_research_focus()
    assert config["schema_version"] == "owner_research_focus/v1"
    assert config["is_portfolio_holdings"] is False
    assert config["is_actionable"] is False
    assert config["grants_investment_authority"] is False
    assert owner_focus_tickers() == ("SSI", "HPG", "PAN", "EVF", "VNM", "FPT", "PVD", "NVL", "POW", "PNJ")
    assert broader_watchlist() == ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
    assert "QNS" in broader_watchlist()
    assert "QNS" not in owner_focus_tickers()
    assert set(owner_focus_tickers()).issubset(set(broader_watchlist()))
