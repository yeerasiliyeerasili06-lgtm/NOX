# Security and privacy

This repository is an **experimental developer preview**, not a trusted installer or a full Windows automation product. Run it only on your own machine in an isolated environment. Review `run.cmd` and `app/src/agent.py` before use: browser QA may fetch `@playwright/mcp@0.0.83` through `npx`. The tool may launch Ollama locally and create local QA reports. No direct ChatGPT delivery is implemented.

Never commit `.env` files, credentials, session cookies, private logs, browser profiles, or local `reports/`. Avoid running as administrator. If you discover a vulnerability, contact the maintainer privately instead of publishing secrets in an issue.

## Licensing status
NOX-authored source is provided under the MIT License; see `LICENSE` and `THIRD_PARTY.md`. Confirm ownership of contributions and review external software licenses before redistribution.
