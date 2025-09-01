import gradio as gr
from orchestrator import load_defaults, orchestrate, manual_github_sync

d = load_defaults()

def run(namespace, space_name, repo_url, hardware, private):
    return orchestrate(namespace, space_name, repo_url, hardware if hardware else None, private, d.get("retry_limit",3))

def run_sync():
    return manual_github_sync()

with gr.Blocks(title="HF Orchestrator — Drop70 TopLevel") as demo:
    gr.Markdown("### HF Orchestrator — Drop70 (Top-Level Files)\nSelf-heals missing GitPython at runtime.\n\n_All files are at the top level of the Space._")

    with gr.Row():
        ns = gr.Textbox(label="Namespace", value=d.get("namespace",""))
        sp = gr.Textbox(label="Space name", value=d.get("space_name",""))
    repo = gr.Textbox(label="Repo URL", value=d.get("repo_url",""))
    hw = gr.Dropdown(label="Hardware", choices=["", "cpu", "t4-small", "a10g-small"], value=d.get("hardware",""))
    priv = gr.Checkbox(label="Private Space", value=bool(d.get("private", True)))

    with gr.Row():
        run_btn = gr.Button("Run")
        sync_btn = gr.Button("Test GitHub Sync")

    out = gr.Textbox(label="Logs", lines=16)

    run_btn.click(run, [ns, sp, repo, hw, priv], out)
    sync_btn.click(run_sync, outputs=out)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860, show_error=True)
