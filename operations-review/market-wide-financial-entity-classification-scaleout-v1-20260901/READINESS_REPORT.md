# Market-Wide Financial Entity Classification Scale-Out V1

**Generated At**: `2026-09-01T00:00:00+00:00`  
**Candidate Denominator (UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS)**: `966`  
**Newly Promoted**: `941`  
**Diagnostics Identity**: `9306fa0ae7b04f04599aad41346babe6b82aee57ba2c444a89927a77863c469e`  

## Outcome distribution

| Outcome | Count |
|---|---:|
| `UNKNOWN` | 25 |
| `corporate` | 927 |
| `insurance` | 6 |
| `securities` | 8 |

## Classification source distribution

| Evidence tier | Count |
|---|---:|
| `exchange_industry_classification` | 933 |
| `statement_template` | 8 |

## Reason-code distribution

| Reason code | Count |
|---|---:|
| `AMBIGUOUS_FINANCIAL_SECTOR_NO_SPECIALIZED_SUBTYPE_EVIDENCE` | 5 |
| `ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD` | 20 |
| `icb_industry_hint positively evidences a governed non-financial sector; no retained balance-sheet template contradicts it` | 102 |
| `icb_industry_hint positively evidences a governed non-financial sector; retained statement_taxonomy='corporate_vas' does not contradict it` | 825 |
| `statement_taxonomy positively evidences the securities-company template; corroborated by icb_industry_hint='AMBIGUOUS_FINANCIAL_SECTOR'` | 8 |
| `statement_taxonomy='financial_specialized_ambiguous' confirms a specialized-financial template; icb_industry_hint='INSURANCE' resolves which one` | 6 |

## Conflicts (0)


## Not-applicable / unsupported security type (0)


## Remaining unknown (25)

Truthful residual: no positive, non-conflicting, non-heuristic evidence resolved these.

- `BCG`: AMBIGUOUS_FINANCIAL_SECTOR_NO_SPECIALIZED_SUBTYPE_EVIDENCE
- `BCO`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `CMP`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `CPH`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `DBW`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `DCV`: AMBIGUOUS_FINANCIAL_SECTOR_NO_SPECIALIZED_SUBTYPE_EVIDENCE
- `HDS`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `HRT`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `HTW`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `HVA`: AMBIGUOUS_FINANCIAL_SECTOR_NO_SPECIALIZED_SUBTYPE_EVIDENCE
- `IBC`: AMBIGUOUS_FINANCIAL_SECTOR_NO_SPECIALIZED_SUBTYPE_EVIDENCE
- `KTW`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `KWA`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `MEG`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `MES`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `PDT`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `PQN`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `SON`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `SRT`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `TC6`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `TDN`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `TVC`: AMBIGUOUS_FINANCIAL_SECTOR_NO_SPECIALIZED_SUBTYPE_EVIDENCE
- `VDB`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `VHI`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
- `VIS`: ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD
