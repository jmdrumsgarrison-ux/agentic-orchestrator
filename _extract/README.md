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

# AO v0.1.1 — Docker

Fixes:
- **PermissionError** when cloning: use **/data** for writable storage (`/data/repo_ro`).
- Clearer error messages in Git tab.
- Friendlier message for OpenAI 429 (quota).

Secrets:
SecretStrippedByGitPush
- `GITHUB_TOKEN` (optional, for private repos)


