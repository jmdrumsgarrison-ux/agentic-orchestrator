---
title: HF Orchestrator — Drop66
emoji: 🚀
colorFrom: yellow
colorTo: purple
sdk: gradio
sdk_version: "4.44.0"
app_file: app.py
pinned: false
license: apache-2.0
---

# HF Orchestrator — Self‑patching Hugging Face Space Deployer

**Deploy any GitHub repo to Hugging Face Spaces** with safe Dockerfile synthesis, auto GPU inference, and a multi‑pass repair loop that patches common build/runtime errors.

## Quick Start
- Add Space secret `HF_TOKEN` (write access).
- Optional for GitHub sync: add Space secret `GITHUB_TOKEN` with `repo` + `workflow` scopes.
- Fill the UI (Namespace, Space name, Git repo URL) and click **Run Agent**.

## Key Features
- Repo fetch (zip/clone) → Dockerfile adopt or synthesize (Python 3.10 slim + essential libs).
- GPU inference detection & hardware request (auto or manual override).
- Multi-pass self repair for target Spaces (libs, CUDA/MMCV, PYTHONPATH, OpenCV headless).
- **GitHub integration** (Drop66+): auto commit, tag, and release zip to your repo when `GITHUB_TOKEN` is set.
