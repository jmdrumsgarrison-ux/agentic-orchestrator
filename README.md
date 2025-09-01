# HF Orchestrator — Drop68 (Space Edition)

**What’s in this drop**
- `app/app.py` — Gradio entrypoint (binds 0.0.0.0:7860 automatically on Spaces)
- `app/orchestrator.py` — includes auto-repair for missing GitPython
- `app/defaults.json` — GUI defaults (Namespace, Space name, Repo URL)
- `requirements.txt` — adds `gitpython`

**How to use (Hugging Face Space)**
1. Create or open your Space (SDK: **Gradio**).
2. Upload the contents of this zip to the Space root (keep the same structure).
3. Spaces will install `requirements.txt` and start `app/app.py` automatically.
4. Open the Space — the UI shows your requested defaults.
