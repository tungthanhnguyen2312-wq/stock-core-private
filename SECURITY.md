# Security Policy

## Scope

This repository publishes a **static dashboard** (HTML/CSS/JS served via GitHub Pages) plus
public documentation. It does not run a server, does not accept user input that reaches a
backend, and does not store credentials or user data client-side. The data pipeline that
produces the CSV/JSON files consumed by the dashboard runs locally and is **not** part of
this repository (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Reporting a Vulnerability

If you find a security issue in the published site (e.g. an XSS vector in how the dashboard
renders CSV/JSON/Markdown data, or a dependency pulled from CDN with a known CVE), please
open a [GitHub issue](https://github.com/tungthanhnguyen2312-wq/market-dashboard/issues) with
a clear description and reproduction steps. Do not
include real portfolio/financial data in reports — sample/synthetic data is enough to
reproduce a rendering bug.

There is no bug bounty program; this is a personal/portfolio project maintained on a
best-effort basis.

## Supported Versions

Only the `main` branch is maintained. There are no tagged releases with independent security
support at this time.
