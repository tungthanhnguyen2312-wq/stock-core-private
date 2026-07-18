# Financial Mapping Registry

Phase 2 chuyển mapping các chỉ tiêu tài chính chuyên sâu sang
`config/financial_item_map.csv`. Mapping deterministic theo thứ tự:

1. exact `item_id`;
2. exact source field;
3. exact normalized label;
4. regex alias;
5. derivation rule khi caller yêu cầu metric;
6. không match thì trả missing, không fuzzy-match.

Mỗi kết quả có `canonical_metric`, `match_method`, `mapping_rule_id`,
`confidence`, `priority`, `sign_multiplier` và `unit_multiplier`. Raw item ID và
raw label vẫn được giữ trong bước melt của `bctc_processor.py`.

## Entity profiles

Các profile hợp lệ: `corporate`, `bank`, `securities`, `insurance`. PAN được khai
báo `corporate`. Ticker không có trong `ticker_entity_profiles.csv` nhận profile
`unknown`, không tự động bị coi là corporate. Rule dùng `entity_type=*` chỉ dành
cho mapping có nghĩa an toàn giữa các loại hình, ví dụ reported OCF.

## Derivation boundary

Registry khai báo công thức EBIT, EBITDA và SG&A. Từ Phase 4, processor chỉ thực
thi các công thức này cho entity profile phù hợp, khi đủ input và sign convention
đã được kiểm tra; xem [advanced_financial_metrics.md](advanced_financial_metrics.md).
Phase 2 không thay đổi period selection/YTD/TTM của OCF. Logic này đã được triển
khai riêng ở Phase 3; xem [operating_cash_flow.md](operating_cash_flow.md).

Diagnostic PAN:

```powershell
python financial_mapping.py --ticker PAN --output reports/financial_mapping_diagnostics_pan.json
```

## Phase 9 registry contract

The default registry requires `financial_item_map.meta.json` with a registry version and provenance. Loading rejects duplicate IDs, equal-priority ambiguous exact matchers, invalid regex, unknown canonical metrics, unsupported entity/report types, invalid sign/unit multipliers, and conflicting exact mappings. The legacy core `ITEM_MAPPING` remains only for core metrics not yet represented by this advanced registry; removing it would break compatibility and was intentionally deferred.
