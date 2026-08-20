import inspect
from provider_financial_semantics import contract,eligible,UNKNOWN,PROVIDER
def test_duration_and_unknown_metadata_block_ratios_only():
 s=contract({'provider':'VCI','statement_family':'income_statement','period_type':'quarterly','warnings':['statement_scope_unknown','currency_and_scale_unknown']});assert s['duration_basis']==UNKNOWN and not eligible('net_margin',s) and s['authority_state']==PROVIDER
def test_balance_instant_and_no_ticker_branch():
 s=contract({'statement_family':'balance_sheet','warnings':[]});assert s['metric_nature']=='instant' and 'if ticker ==' not in inspect.getsource(contract)
