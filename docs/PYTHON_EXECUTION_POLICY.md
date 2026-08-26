# Python execution policy

Canonical interpreter for this workspace:

`C:\Program Files\Python313\python.exe` (CPython 3.13)

Roles:

| Role | Interpreter |
|---|---|
| PRODUCER_PYTHON | system 3.13 |
| CONSUMER_PYTHON | same |
| TEST_PYTHON_POLICY | same |
| DASHBOARD_BUILD_PYTHON | not required; frontend uses Node/Tailwind |
| RUNTIME_PYTHON_POLICY | do not execute dashboard-runtime as source; run Producer scripts with `STOCK_LOOKUP_RUNTIME_ROOT=C:\Projects\StockLookup\dashboard-runtime` |
| BENCHMARK_PYTHON_POLICY | same system interpreter |

Obsolete environments (removed):

- `.phase3a-benchmark-venv`
- `stock-core-private\.test-venv`
- `dashboard-runtime\.venv`

Optional override: `STOCK_LOOKUP_PYTHON` on Producer `sync_and_publish.bat` only. Ambient `python` on PATH should resolve to the same 3.13 install.
