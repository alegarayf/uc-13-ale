# Changelog

## uc13-remediation-plan — 2026-06-23

- T2 (Route A metadata router): Added `databricks/agents/shared/_types.py` (`RouteResult`), `route_chunks.py` (SQL metadata routing with post-SQL filters), and `tests/test_route_chunks.py` (mocked Spark filter/shape/error coverage). Circular-import shim and `tier_filter=None` default preserve control-arm parity for T5 wiring. See `.dev/decision-logs/T2-route-chunks.md`.
