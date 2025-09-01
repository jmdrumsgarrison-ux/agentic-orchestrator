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

# AO v0.3.4 — Docker (Workers scaffold)

What's new
- `ops/plan.md` now includes a **Workers** section scaffold:
  ```yaml
  workers:
    - name: (none yet)
      repo: (to be assigned)
      status: idle
  ```
- Everything else stays the same: single-source repo (`AO_DEFAULT_REPO`), auto branch, auto plan/log,
  home/identity hardening, and auto-commit heuristic.
