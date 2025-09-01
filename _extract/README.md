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

# AO v0.1.3 — Docker

Changes:
- Git working directory set to **/tmp/repo_ro** (writable in HF Docker Spaces).
- Automatic fallback chain: `/tmp/repo_ro` → `/app/repo_ro`.
- Clearer error messages.

Secrets:
SecretStrippedByGitPush
- `GITHUB_TOKEN` (optional for private repos)

