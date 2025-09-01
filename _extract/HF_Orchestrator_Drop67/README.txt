HF Orchestrator — Drop67
========================

This package applies your requested GUI defaults:

- Namespace: JmDrumsGarrison
- Space name: track-anything
- Repo URL: https://github.com/gaomingqi/Track-Anything
- Hardware: (auto-detect, leave blank) 
- Private: ON

Files
-----
- app/defaults.json — where the defaults are stored
- app/orchestrator.py — loads defaults (stub here; drop into your main app)
- app/app.py — Gradio UI wired to defaults
- requirements.txt — minimal deps
- setup.bat — one-time env setup (Windows)
- deploy.bat — runs the app (Windows)

Logs are written to G:\HuggingFace\HF_Agent_Package\Logs.
