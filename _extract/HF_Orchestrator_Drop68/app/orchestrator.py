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
    """
    Try to import a module; if missing, pip install and re-import.
    Returns the imported module object.
    """
    try:
        return importlib.import_module(modname)
    except ModuleNotFoundError as e:
        if log: log(f"[auto-repair] Missing module '{modname}'. Attempting self-install...")
        pkg = pip_name or modname
        cmd = [sys.executable, "-m", "pip", "install", pkg]
        if extra_args:
            cmd.extend(extra_args)
        try:
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            if log: log(f"[auto-repair] Installed '{pkg}'. Re-importing...")
            return importlib.import_module(modname)
        except Exception as ie:
            if log: log(f"[auto-repair] Failed to install '{pkg}': {ie}")
            raise e

def _default_logger_factory(logs):
    def _log(msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts}  {msg}"
        logs.append(line)
    return _log

def orchestrate(namespace, space_name, repo_url, hardware=None, private=True, retry_limit=3, logs=None):
    """
    Demo orchestrate that exercises GitPython and shows auto-repair if it's missing.
    """
    logs = logs if logs is not None else []
    log = _default_logger_factory(logs)

    log("Orchestrator starting (Drop68 demo).")
    log(f"Inputs: namespace={namespace}, space={space_name}, repo={repo_url}, hardware={hardware or '(auto)'}, private={private}")
    log("Checking GitPython...")
    git_mod = _ensure_module("git", pip_name="gitpython", log=log)

    # Use the module lightly to verify it's present
    log(f"GitPython version: {getattr(git_mod, '__version__', 'unknown')}")

    # In the full app, we'd proceed with real logic; here just pretend success
    log("Proceeding with repo operations (omitted in demo).")
    log("DONE")
    return "\n".join(logs)

def manual_github_sync(logs=None):
    logs = logs if logs is not None else []
    log = _default_logger_factory(logs)
    log("Manual GitHub sync (demo).")
    _ensure_module("git", pip_name="gitpython", log=log)
    log("Sync ok (demo).")
    return "\n".join(logs)
