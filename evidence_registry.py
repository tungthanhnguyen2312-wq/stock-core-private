"""Read-only unified registry over append-only evidence sidecars."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any, Iterable
from financial_observations import read_observations, store_path, canonical_records
import semantic_evidence_bridge as bridge

EVIDENCE=Path("data")/"official-evidence"
FILES={"qualification":"qualification_citations.jsonl","share_basis":"share_basis_citations.jsonl","market_price":"market_price_citations.jsonl","ebitda":"ebitda_component_citations.jsonl"}
SUPPORTED_SHARE={"period_end_shares_outstanding","weighted_average_basic_shares_outstanding","weighted_average_diluted_shares_outstanding","valuation_date_shares_outstanding"}
DEFAULT_ENTITIES={"HPG":"corporate","VNM":"corporate","VCB":"bank"}

def _rows(path: Path) -> list[dict[str,Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]

def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def _id(kind: str, row: dict[str,Any]) -> str:
    return f"{kind}:{row.get('ticker','')}:{row.get('reporting_period') or row.get('trading_date','')}:{row.get('identity_type') or row.get('raw_item_id') or row.get('metric') or row.get('evidence_id')}:{row.get('citation_id') or row.get('observation_id') or row.get('evidence_id')}"

class EvidenceRegistry:
    """No writes: indexes existing evidence into queryable, lineage-bearing facts."""
    def __init__(self, runtime_root: Path, entities: dict[str,str]|None=None):
        self.root=Path(runtime_root); self.entities=entities or DEFAULT_ENTITIES; self.documents={}; self.facts=[]; self.issues=[]
    def load(self) -> "EvidenceRegistry":
        base=self.root/EVIDENCE; manifest=base/"manifest.json"
        try: records=json.loads(manifest.read_text(encoding="utf-8-sig")).get("records",[])
        except (OSError,json.JSONDecodeError): self.issues.append({"reason":"manifest_unreadable"}); records=[]
        for d in records:
            doc=Path(d.get("archive_document_path") or base/str(d.get("filename","")))
            valid=doc.is_file() and _sha(doc)==d.get("sha256")
            self.documents[d.get("evidence_id")]=d|{"_valid":valid,"_path":str(doc)}
            if not valid:self.issues.append({"reason":"document_hash_mismatch","evidence_id":d.get("evidence_id")})
        obs={r.get("observation_id"):r for r in read_observations(store_path(self.root))}
        for kind,name in FILES.items():
            for row in _rows(base/name):
                evidence=row.get("evidence_id"); citation=row.get("citation_id"); oid=row.get("observation_id")
                metric=row.get("identity_type") or row.get("raw_item_id") or row.get("metric")
                status="qualified" if evidence in self.documents and self.documents[evidence]["_valid"] else "invalid"
                if kind!="market_price" and evidence not in self.documents:self.issues.append({"reason":"dangling_evidence","citation_id":citation})
                if kind=="qualification" and oid not in obs:self.issues.append({"reason":"dangling_observation","citation_id":citation})
                if kind=="share_basis" and metric not in SUPPORTED_SHARE:self.issues.append({"reason":"unsupported_metric_semantics","citation_id":citation})
                self.facts.append({"identity":_id(kind,row),"kind":kind,"ticker":row.get("ticker"),"period":row.get("reporting_period") or row.get("trading_date"),"metric":metric,"source":kind,"qualification_status":row.get("qualification_status",status),"citation_id":citation,"observation_id":oid,"document_hash":self.documents.get(evidence,{}).get("sha256"),"evidence_id":evidence,"lineage":{"document":evidence,"observation":oid,"supersedes":row.get("supersedes_citation_ids",[])},"raw":row})
        self._derived()
        self._integrity()
        return self
    def _derived(self)->None:
        try:
            c=canonical_records(store_path(self.root),self.entities)
            enriched=bridge.reconcile_metric_identities(bridge.enrich_canonical_records(c,self.root))
        except Exception as exc:
            self.issues.append({"reason":"canonicalization_unavailable","detail":type(exc).__name__}); return
        for ticker,records in enriched.items():
            for r in records:
                if "evidence" not in r: continue
                p=r.get("period_identity",{}).get("period")
                self.facts.append({"identity":f"derived:{ticker}:{p}:{r['canonical_metric']}:{','.join(sorted(r.get('observation_ids',[])))}","kind":"derived","ticker":ticker,"period":p,"metric":r["canonical_metric"],"source":"canonical_derived" if r.get("derivation_status")=="derived" else "canonical_direct","qualification_status":r.get("quality_state"),"citation_id":None,"observation_id":None,"document_hash":None,"evidence_id":None,"lineage":{"observation_ids":r.get("observation_ids",[]),"evidence":r.get("evidence")},"raw":r})
    def _integrity(self)->None:
        groups={}
        for f in self.facts: groups.setdefault((f["ticker"],f["period"],f["metric"],f["source"],f["raw"].get("raw_statement_type")),[]).append(f)
        for key,items in groups.items():
            ids={x["citation_id"] or x["identity"] for x in items}
            if len(ids)>1 and items[0]["source"]!="canonical_direct":
                successors=[x for x in items if set(x["lineage"].get("supersedes",[]))==ids-{x["citation_id"]}]
                if len(successors)!=1:self.issues.append({"reason":"duplicate_or_supersession_conflict","identity":key})
        for f in self.facts:
            if self.entities.get(f["ticker"])=="bank" and f["metric"]=="total_debt":self.issues.append({"reason":"bank_deposits_aliased_to_debt","identity":f["identity"]})
    def query(self, **filters: Any)->list[dict[str,Any]]:
        allowed={"ticker","period","metric","source","qualification_status","document_hash","citation_id","observation_id"}
        bad=set(filters)-allowed
        if bad: raise ValueError(f"unsupported query fields: {sorted(bad)}")
        return [f for f in self.facts if all(f.get(k)==v for k,v in filters.items())]
    def report(self)->dict[str,Any]:
        return {"version":"1.0.0","documents":len(self.documents),"facts":len(self.facts),"issues":self.issues,"capabilities":{"ticker_period_metric_query":True,"document_hash_query":True,"lineage_query":True,"append_only_validation":True,"transactional_supersession":False,"concurrent_writes":False}}

def main(argv:Iterable[str]|None=None)->int:
    p=argparse.ArgumentParser(description="Read-only Evidence Registry MVP")
    p.add_argument("--runtime-root",required=True); p.add_argument("--output",required=True,help="explicit caller-supplied report path")
    a=p.parse_args(argv); out=Path(a.output)
    if out.exists(): p.error("output already exists; registry never overwrites")
    reg=EvidenceRegistry(Path(a.runtime_root)).load(); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(reg.report(),indent=2,sort_keys=True),encoding="utf-8")
    return 0
if __name__=="__main__": raise SystemExit(main())