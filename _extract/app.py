
import gradio as gr
import py_compile
from orchestrator import orchestrate, OrchestratorError, manual_github_sync
import json, os

# Preflight compile of orchestrator.py
try:
    py_compile.compile("orchestrator.py", doraise=True)
except Exception as e:
    with gr.Blocks(title="HF Orchestrator — Drop66", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# HF Orchestrator — Drop66")
        gr.Markdown("**Self-check failed**: orchestrator.py has a syntax error.")
        gr.Textbox(label="Compiler error", value=str(e), lines=10)
    if __name__ == "__main__":
        demo.queue(status_update_rate=1).launch(max_threads=8, )
    raise SystemExit(1)

PREFS_PATH = "/home/user/app/.orchestrator_prefs.json"

def _load_prefs():
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_prefs(d):
    try:
        with open(PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass

with gr.Blocks(title="HF Orchestrator — Drop66", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# HF Orchestrator — Drop66")
    with gr.Row():
        ns = gr.Textbox(label="Target Namespace (username or org)", placeholder="your-username-or-org", scale=1)
        sp = gr.Textbox(label="Target Space (new or existing)", placeholder="track-anything", scale=1)
    repo = gr.Textbox(label="Git repo URL", placeholder="https://github.com/<user>/<repo>", lines=1)
    with gr.Row():
        hardware = gr.Textbox(label="Hardware (optional, e.g., t4-small)", placeholder="Leave blank for auto")
        private = gr.Checkbox(label="Private target Space?", value=True)
    run_btn = gr.Button("Run Agent 🚀", variant="primary")
    sync_btn = gr.Button("Test GitHub Sync 📦", variant="secondary")
    logs = gr.Textbox(label="Logs", lines=24, autoscroll=True)
    status = gr.Label(label="Final Status")

    def load_defaults():
        p = _load_prefs()
        return (
            p.get("namespace", ""),
            p.get("space", ""),
            p.get("repo", ""),
            p.get("hardware", ""),
            p.get("private", True),
        )

    def save_prefs(ns_, sp_, repo_, hardware_, private_):
        _save_prefs({"namespace": ns_.strip(), "space": sp_.strip(), "repo": repo_.strip(), "hardware": (hardware_ or "").strip(), "private": bool(private_)})
        return None

    def start():
        return "Starting orchestration…", ""

    def run(ns, sp, repo, hardware, private):
        try:
            for out in orchestrate(ns.strip(), sp.strip(), repo.strip(), (hardware or "").strip() or None, bool(private)):
                if isinstance(out, dict) and "log" in out:
                    logs_text = "\n".join(out.get("log", []))
                    status_val = out.get("status", "")
                    yield logs_text, status_val
                else:
                    yield str(out), ""
        except OrchestratorError as e:
            yield f"ERROR: {str(e)}", "ERROR"
        except Exception as e:
            yield f"Unexpected error: {str(e)}", "ERROR"

    demo.load(load_defaults, inputs=None, outputs=[ns, sp, repo, hardware, private])
    run_btn.click(save_prefs, [ns, sp, repo, hardware, private], None)
    run_btn.click(start, [], [logs, status])
    run_btn.click(run, [ns, sp, repo, hardware, private], [logs, status])
    sync_btn.click(lambda: "\n".join(manual_github_sync([])["log"]), None, logs)

if __name__ == "__main__":
    demo.queue(status_update_rate=1).launch(max_threads=8, show_error=True)
