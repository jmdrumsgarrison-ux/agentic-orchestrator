HF Orchestrator — Drop68
========================

What's new
----------
- Adds **GitPython** to requirements (`gitpython>=3.1.43`).
- **Auto-repair**: if the app hits `ModuleNotFoundError: git`, it installs `gitpython` at runtime and retries the import.
- Keeps your GUI defaults:
  - Namespace: JmDrumsGarrison
  - Space name: track-anything
  - Repo URL: https://github.com/gaomingqi/Track-Anything
  - Private: ON
  - Hardware: (auto)

How it works
------------
- `orchestrator._ensure_module("git", pip_name="gitpython")` attempts import;
  on failure, it runs `pip install gitpython` and re-imports.
- `app.py` calls `orchestrate(...)`, which exercises GitPython to verify the fix.

Files
-----
- app/defaults.json
- app/orchestrator.py
- app/app.py
- requirements.txt
- setup.bat, deploy.bat
