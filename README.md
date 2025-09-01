---
title: Agentic Orchestrator (AO)
emoji: 🧠
colorFrom: green
colorTo: blue
sdk: docker
sdk_version: "1"
app_file: app.py
pinned: false
---

# AO v0.3.3 — Docker (Opinionated, no allowlist)

Changes
- **ALLOWLIST_REPOS removed** from the write path. AO uses **AO_DEFAULT_REPO** as the single source of truth.
- UI simplified: **no repo textbox**. Click **Run** and AO writes to AO_DEFAULT_REPO.
- Keeps prior hardening: HOME set, repo-local git identity, auto-branch, auto plan/log, auto-commit heuristic.

Config
- `GITHUB_TOKEN` (required, repo write perms)
- `AO_DEFAULT_REPO` (required, full https URL to the AO server repo)
- `AO_AUTO_COMMIT` (optional; default true)
- `OPENAI_API_KEY` (optional, Ask tab)
