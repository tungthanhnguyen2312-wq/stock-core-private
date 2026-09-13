# Stock Lookup — Public / Open-Core Boundary

Stock Lookup uses an **open-core** model: this repository is the public, reproducible engineering core, while sensitive operational data, credentials, portfolio state, and any future proprietary operating layer remain outside the public repository.

This document is a project-governance boundary. It does not change the terms of the repository's `LICENSE`.

## Public core

The public repository may contain:

- deterministic analytics and feature contracts;
- evidence/provenance and point-in-time semantics;
- canonicalization, validation, and fail-closed gating logic;
- non-sensitive provider adapters and request/response schemas that do not expose credentials;
- reproducible tests, fixtures, sample data, and documentation that are safe to redistribute;
- generic valuation, technical, market-structure, and research infrastructure;
- governance documents that explain authority, limitations, and reproducibility.

The public core should remain useful on its own for research, learning, verification, and community contribution.

## Outside the public boundary

The following must not be committed to this repository unless the owner explicitly reclassifies them and confirms redistribution rights:

- API keys, secrets, access tokens, certificates, cookies, session credentials, or credential-bearing environment files;
- paid, licensed, private, or provider-restricted raw datasets and retained evidence payloads;
- production databases, runtime snapshots, backups, or machine-specific operator state;
- private portfolios, holdings, order history, position sizes, broker/account configuration, or personal financial information;
- execution credentials, order-routing settings, slippage/impact parameters tied to a private execution setup, or private risk limits;
- proprietary calibration outputs, live alpha/ranking thresholds, private strategy-selection policy, or other operating rules intentionally reserved as a competitive layer;
- private infrastructure topology, secret paths, recovery material, or operational logs containing sensitive details;
- third-party material that Stock Lookup does not have the right to redistribute.

## Data and evidence

Public source code does not imply that the underlying market data, financial statements, exchange documents, provider responses, or retained evidence artifacts are freely redistributable. Each data source keeps its own terms and authority status.

When examples are needed, prefer synthetic, redacted, public-domain, or explicitly redistributable fixtures.

## Investment and execution boundary

The public core is research and decision-support infrastructure. Publication of a model, feature, valuation method, or research framework does not automatically publish:

- a live portfolio;
- a production execution policy;
- a position-sizing policy;
- calibrated trading thresholds;
- private operational signals;
- point-in-time or execution authority that has not been explicitly promoted by project governance.

Stock Lookup's existing fail-closed authority rules continue to apply independently of whether code is public.

## Future commercial products

The owner may offer hosted services, private datasets, support, enterprise integrations, proprietary modules, or other products under separate terms. Code already distributed from this repository remains governed by the license under which it was distributed.

A future private or commercial layer should integrate through explicit contracts rather than silently weakening or replacing the public core's evidence and determinism guarantees.

## Contribution boundary

Community contributions are welcome when they are reproducible and safe to redistribute. Contributions must not include private datasets, secrets, copied proprietary code, or material whose redistribution rights are unclear.

See `CONTRIBUTING.md` for contribution and licensing expectations.
