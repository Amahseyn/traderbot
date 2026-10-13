from traderbot.risk.manager import RiskLimits
from traderbot.risk.runtime import clear_risk_managers, configure_risk_manager, get_risk_manager


def test_risk_managers_are_scoped():
    clear_risk_managers()
    configure_risk_manager(RiskLimits(capital_cap=100.0), scope="BTCIRT")
    configure_risk_manager(RiskLimits(capital_cap=200.0), scope="ETHIRT")
    assert get_risk_manager("BTCIRT").limits.capital_cap == 100.0
    assert get_risk_manager("ETHIRT").limits.capital_cap == 200.0
    clear_risk_managers()
