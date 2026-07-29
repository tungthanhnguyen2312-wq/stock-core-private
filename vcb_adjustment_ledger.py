"""VCB-only shadow adjustment ledger; never writes or rewrites OHLCV."""
import hashlib,json
VERSION="1.0.0"
def _canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"))
def build_shadow_ledger(event,factor,share_before=None,share_after=None,price_adjustment_date=None):
 if event.get("qualification")!="qualified" or factor.get("application")!="shadow_only":raise ValueError("qualified_event_and_shadow_factor_required")
 if factor["event_record_id"]!=event["record_id"]:raise ValueError("event_factor_lineage_mismatch")
 if price_adjustment_date is not None:raise ValueError("price_adjustment_date_not_directly_qualified")
 if share_before is not None or share_after is not None:raise ValueError("qualified_before_after_share_counts_required")
 entry={"ledger_version":VERSION,"event_record_id":event["record_id"],"factor_id":factor["factor_id"],"ticker":"VCB","ratio":event["share_ratio"],"share_quantity_effective_date":event["date_lineage"]["issuance_date"],"market_price_adjustment_date":None,"listing_completion_date":event["date_lineage"]["listing_date"],"source_hash":event["source_hash"],"citation_id":event["citation_id"],"factor_lineage":factor["lineage"],"share_basis_status":"multiplier_only","share_basis_before":None,"share_basis_after":None,"price_factor_applied":False,"shadow_adjusted_series":False,"blockers":["MARKET_PRICE_ADJUSTMENT_DATE_NOT_DIRECTLY_QUALIFIED","QUALIFIED_BEFORE_AFTER_SHARE_COUNTS_UNAVAILABLE"]};entry["ledger_entry_id"]="vca-"+hashlib.sha256(_canon(entry).encode()).hexdigest();return entry