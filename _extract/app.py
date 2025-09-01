
import os, gradio as gr
from datetime import datetime

APP_VERSION = "AO v0.8.7"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")

BANNER = f"### {APP_VERSION} — GPT model: `{MODEL}` • Rich text → Markdown • Uploads"

def echo_markdown(md_text, files):
    reply = ["### Received Markdown", md_text or "(_empty_)"]
    if files:
        reply.append("### Files")
        for f in files:
            reply.append(f"- {os.path.basename(f)}")
    return "\n".join(reply)

with gr.Blocks(css="""
#rt-wrap { border: 1px solid #CCD; border-radius: 8px; padding: 8px; }
#rt-toolbar button { margin-right: 6px; padding: 4px 8px; }
#rt-area { min-height: 160px; outline: none; padding: 8px; }
""") as demo:
    gr.Markdown(BANNER)

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("#### Rich text editor (HTML → Markdown)")
            gr.HTML(
                '''
                <script src="https://cdn.jsdelivr.net/npm/turndown@7.1.2/dist/turndown.js"></script>
                <div id="rt-wrap">
                  <div id="rt-toolbar">
                    <button onclick="document.execCommand('bold', false, null)"><b>B</b></button>
                    <button onclick="document.execCommand('italic', false, null)"><i>I</i></button>
                    <button onclick="document.execCommand('insertUnorderedList', false, null)">• List</button>
                    <button onclick="document.execCommand('insertOrderedList', false, null)">1. List</button>
                  </div>
                  <div id="rt-area" contenteditable="true" spellcheck="true">
                    Type here… (this is HTML under the hood, converted to Markdown).
                  </div>
                </div>
                <script>
                window.__getEditorMarkdown = function(){
                  const area = document.getElementById('rt-area');
                  const html = area ? area.innerHTML : "";
                  const td = new TurndownService({headingStyle:"atx"});
                  return td.turndown(html || "");
                };
                </script>
                '''
            )
            use_btn = gr.Button("Use editor content")
            md_box = gr.Textbox(label="Markdown (from editor)", lines=8, placeholder="Press the button above to pull from editor")
            use_btn.click(fn=None, inputs=None, outputs=md_box, js="() => window.__getEditorMarkdown()")

            files = gr.Files(label="Upload files (optional)", type="filepath")
            send = gr.Button("Send")
            out = gr.Markdown()

            send.click(fn=echo_markdown, inputs=[md_box, files], outputs=out)

    gr.Markdown(f"_Built at {datetime.utcnow().isoformat()}Z — Gradio {gr.__version__}_")

if __name__ == "__main__":
    demo.launch()
