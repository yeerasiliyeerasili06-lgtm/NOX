# Experimental Preview — 2026-10-18

This is the research/QA candidate only, not NOX 0.15 GUI or the unverified integrated RC1.

Features: Python documentation web research; bounded page verification; independent QA checks; offline tests; manifest validation; locally stored redacted handoff reports.

Reported tests: 57 core + 25 cross-component = 82 offline passes (Linux). No Windows end-to-end acceptance claim.

Known limitations: browser test requires external dependencies and an Ollama model; direct ChatGPT report submission is absent; prior `pathlib` Windows failure is not proven resolved; previous public QA release may contain an older source asset.

Security: no credentials should be committed. Review source, commands, and package provenance before publishing. No permission to modify third-party computers or accounts is implied.
