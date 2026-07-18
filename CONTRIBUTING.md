# Contributing

Thanks for your interest in this project. Please read this before opening an issue or PR —
the scope here is narrower than it might look at first glance.

## What this repository actually contains

This repo (`market-dashboard`) is the **public dashboard site** for a personal Vietnamese
stock-market data project. It is intentionally *not* the full project:

- The data pipeline (price backfill, metadata, macro, news, financial reports, AI report
  generation — all Python) runs **locally only** and is not published here.
- The underlying database and generated datasets are personal data assets and are gitignored
  by design (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full split).

What **is** in this repo and open to contribution: the static frontend (`dashboard.html`,
`screener.html`, `analysis.html`/`analysis.js`, `signals.html`, `about.html`, `archive.html`,
`macro.html`, the `index.html` redirect stub, `app.js`, `style.css`, `assets/css/` and `assets/js/`
shell files) and the documentation in `docs/`. `nav.css` is legacy — only the archived static
reports (`playbook-*.html`, `report-*.html`) still use it.

## Ways to contribute

- **Bug reports on the dashboard** (rendering, filters, broken links, dark-mode issues) —
  open an issue with your browser/OS and steps to reproduce.
- **Documentation fixes** in `docs/` or `README.md` — typos, unclear steps, broken links.
- **Frontend improvements** (`app.js`, `style.css`, `nav.css`, the `.html` pages) — please
  keep the existing IDs that `app.js` depends on (`ai-report`, `report-date`, `last-updated`,
  `filter-exchange`, `filter-industry`, `market-table`, `table-status`) and the dark-mode CSS
  variable system in `style.css` intact; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#quy-ước-ui-giữ-khi-sửa-giao-diện).

## What's out of scope for PRs

- Changes to the data pipeline, financial-report processor, or stock analyzer — that code
  isn't in this repository, so there's nothing here to submit a PR against.
- Investment advice, trading signals, or anything implying the dashboard's output is a
  recommendation — this project is data tooling, not financial advice.

## Submitting a change

1. Fork the repo and create a branch from `main`.
2. Keep changes focused — one fix/feature per PR.
3. Test locally by serving the site (`python -m http.server 8000`) and checking the page(s)
   you touched in a browser, both light data states (empty/missing CSV) and normal data.
4. Open a PR describing what changed and why.

By submitting a contribution, you confirm that you have the right to submit it and
grant Nguyễn Thành Tùng permission to use, modify, and include that contribution in
this repository. This does not grant repository users a general license to use,
copy, modify, or redistribute the repository.
