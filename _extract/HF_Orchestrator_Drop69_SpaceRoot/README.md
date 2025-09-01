# HF Orchestrator — Drop69 (Space Edition, root-level)

**Structure (all files in Space root):**
- `app.py` — Gradio entrypoint
- `orchestrator.py` — auto-repair for missing GitPython
- `defaults.json` — GUI defaults (Namespace, Space name, Repo URL)
- `requirements.txt` — includes `gitpython`

**Use on Hugging Face Spaces:**
1. Open your Space (SDK: Gradio).
2. Upload all files from this zip directly into the **Space root** (no `/app` folder).
3. Build will install `requirements.txt` and run `app.py` automatically.
