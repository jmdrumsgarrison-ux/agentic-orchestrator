import json, os, subprocess, sys, time, importlib

DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "defaults.json")

def load_defaults():
    try:
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "namespace": "",
            "space_name": "",
            "repo_url": "",
            "hardware": "",
            "private": True,
            "retry_limit": 3,
            "cache_settings_on_startup": True,
            "show_github_sync_button": True,
            "auto_detect_gpu": True
        }

def _ensure_module(modname, pip_name=None, extra_args=None, log=None):
    try:
        return importlib.import_module(modname)
    except ModuleNotFoundError as e:
        if log: log(f"[auto-repair] Missing module '{modname}'. Installing...")
        pkg = pip_name or modname
        cmd = [sys.executable, "-m", "pip", "install", pkg]
        if extra_args:
            cmd.extend(extra_args)
        subprocess.check_call(cmd)
        if log: log(f"[auto-repair] Installed '{pkg}'. Re-importing...")
        return importlib.import_module(modname)

def _logger(logs):
    def _log(msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        logs.append(f"{ts}  {msg}")
    return _log

def orchestrate(namespace, space_name, repo_url, hardware=None, private=True, retry_limit=3, logs=None):
    logs = logs if logs is not None else []
    log = _logger(logs)

    log("Orchestrator starting (Drop68 Space).")
    log(f"Inputs: namespace={namespace}, space={space_name}, repo={repo_url}, hardware={hardware or '(auto)'}, private={private}")
    _ensure_module("git", pip_name="gitpython", log=log)
    log("GitPython OK.")
    # Real orchestrate logic would continue here...
    log("DONE")
    return "\n".join(logs)

def manual_github_sync(logs=None):
    logs = logs if logs is not None else []
    log = _logger(logs)
    log("Manual GitHub sync (demo).")
    _ensure_module("git", pip_name="gitpython", log=log)
    log("Sync ok (demo).")
    return "\n".join(logs)
