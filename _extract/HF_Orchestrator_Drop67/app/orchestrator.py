import json, os

DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "defaults.json")

def load_defaults():
    try:
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Safe fallbacks mirroring Drop66 behavior
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
