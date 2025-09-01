import gradio as gr
from orchestrator import load_defaults

d = load_defaults()

def run_orchestrator(namespace, space_name, repo_url, hardware, private):
    # This is a stub: in your real app, you call orchestrate(...)
    # Here we just echo to demonstrate defaults are wired correctly.
    logs = [
        f"Namespace: {namespace}",
        f"Space name: {space_name}",
        f"Repo URL: {repo_url}",
        f"Hardware: {hardware or '(auto)'}",
        f"Private: {private}",
        "Starting (demo stub)...",
        "OK"
    ]
    return "\n".join(logs)

with gr.Blocks(title="HF Orchestrator — Drop67") as demo:
    gr.Markdown("### HF Orchestrator — Drop67 (GUI defaults applied)")

    with gr.Row():
        ns = gr.Textbox(label="Namespace", value=d.get("namespace",""))
        sp = gr.Textbox(label="Space name", value=d.get("space_name",""))
    repo = gr.Textbox(label="Repo URL", value=d.get("repo_url",""))
    hw = gr.Dropdown(label="Hardware", choices=["", "cpu", "t4-small", "a10g-small"], value=d.get("hardware",""))
    priv = gr.Checkbox(label="Private Space", value=bool(d.get("private", True)))

    run_btn = gr.Button("Run (Demo)")
    out = gr.Textbox(label="Logs", lines=12)

    run_btn.click(run_orchestrator, [ns, sp, repo, hw, priv], out)

if __name__ == "__main__":
    # Bind to 0.0.0.0 so Docker/Spaces can expose it
    demo.queue().launch(server_name="0.0.0.0", server_port=7860, show_error=True)
