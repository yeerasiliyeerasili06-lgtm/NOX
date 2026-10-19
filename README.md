# NOX — Web Research & QA Experimental Preview

> Experimental source preview, **not** a complete NOX desktop application or installer.

This snapshot contains a web-research core, a QA runner, offline unit tests, package integrity checking, and locally saved redacted handoff summaries. It is intended for developers and experimenters.

## Status

- 82 offline tests were reported passing in an isolated Linux environment on 2026-10-18.
- Windows browser scenarios, desktop GUI integration, and direct ChatGPT report delivery have **not** been validated in this snapshot.
- No general Windows autonomous control, guaranteed autonomous learning, or full unattended workflow is claimed.

## Contents

- `app/src/`: research agent and outcome/experience logic
- `qa_main.py`, `qa_worker.py`: QA runner
- `tests/`, `app/tests/`: offline tests
- `verify_package.py`, `manifest.json`: package integrity verification
- `offline_check.cmd`: offline check on Windows
- `run.cmd`: optional browser QA requiring dependencies; **may fetch Playwright MCP via npx**, so review before executing

## Requirements

Windows 10/11, Python 3, Node.js/npx, Ollama with `qwen3.5:4b-q4_K_M`, and Playwright MCP prerequisites for browser QA. Do not overwrite an existing NOX installation. For Linux, only offline Python tests are relevant.

## Privacy & safety

Reports are saved locally; this snapshot does not directly send a message to ChatGPT. Review commands and third-party dependencies before running. Use an isolated environment and do not grant elevated system permissions.

## Licensing

NOX-authored source is offered under the MIT License (see `LICENSE`). External dependencies have their own terms (see `THIRD_PARTY.md`). The maintainer should confirm rights to all contributions before publication.

See `RELEASE_NOTES.md` for known limitations and `README_先看.txt` for original technical notes.

## Public repository setup

This is a **source preview**. There is no Windows installer or general-purpose desktop assistant in this archive. Generated reports, local experience databases and credentials should never be committed. See `SECURITY.md`.
