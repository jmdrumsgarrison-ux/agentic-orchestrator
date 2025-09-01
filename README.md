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

# AO v0.5.4r1 — Docker (Self‑Knowledge + Repo Search)

New vs 0.5.4
- **Ask me anything about myself** and I’ll search my repo docs:
  - Freeform questions are matched against `ops/plan.md`, `ops/logbook.md`, `ops/context.yaml`.
  - Returns **quoted snippets with file + line numbers**.
- Still supports: friendly intro, slot‑filling **create HF Space from GitHub repo**, dry‑run, and **logbook writes**.

Secrets
- `GITHUB_TOKEN`, `HF_TOKEN`, `AO_DEFAULT_REPO`, (`HF_NAMESPACE` optional), `JOBS_MAX_PER_DAY`.
