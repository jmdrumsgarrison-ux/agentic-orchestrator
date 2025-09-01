
import os, gradio as gr
from datetime import datetime

APP_VERSION = "AO v0.8.8"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "")

# Optional OpenAI
_client = None
def _get_openai():
    global _client
    if _client is not None:
        return _client
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
        return _client
    except Exception:
        return None

BANNER = f"### {APP_VERSION} — GPT model: `{MODEL}` • Rich editor • Files"

SYSTEM_PROMPT = "You are AO. Be concise, helpful, and resilient. Understand Markdown bullets produced by the editor."

def respond(chat_history, md_text, files):
    # chat_history: list of {'role','content'} for Chatbot(type='messages')
    chat_history = chat_history or []
    user_content = md_text or ""
    if files:
        # append a small note so the model knows filenames exist
        try:
            names = [os.path.basename(getattr(f, 'name', str(f))) for f in files]
            user_content += "\n\n(Attached files: " + ", ".join(names) + ")"
        except Exception:
            pass

    # append user msg
    chat_history.append({"role": "user", "content": user_content})

    client = _get_openai()
    if client is None:
        # echo fallback
        assistant_text = "Echo (no API key configured):\n\n" + (user_content or "_(empty)_")
    else:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role":"system","content":SYSTEM_PROMPT}] + chat_history,
                temperature=0.2,
            )
            assistant_text = resp.choices[0].message.content or "OK."
        except Exception as e:
            assistant_text = f"(OpenAI error: {e})"

    chat_history.append({"role": "assistant", "content": assistant_text})
    # Clear hidden md field after send
    return chat_history, ""

with gr.Blocks(fill_height=True, theme=gr.themes.Soft(), css=) as demo:
    gr.Markdown(BANNER)

    with gr.Row(equal_height=True):
        with gr.Column(scale=3):
            chat = gr.Chatbot(type="messages", height=520, label="Chat")
            state = gr.State([])

        with gr.Column(scale=2):
            # Rich editor (HTML) with simple toolbar; converted to Markdown via JS on Send
            gr.Markdown("#### Compose")
            editor = gr.HTML(value=r'''
<div id="rt-wrap">
  <div id="rt-toolbar">
    <button onclick="document.execCommand('bold', false, null)"><b>B</b></button>
    <button onclick="document.execCommand('italic', false, null)"><i>I</i></button>
    <button onclick="document.execCommand('insertUnorderedList', false, null)">• List</button>
    <button onclick="document.execCommand('insertOrderedList', false, null)">1. List</button>
    <button onclick="document.execCommand('insertLineBreak', false, null)">⏎</button>
  </div>
  <div id="rt-area" contenteditable="true" spellcheck="true" aria-label="Message editor"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/turndown@7.1.2/dist/turndown.js"></script>
<script>
  window.__pullMarkdown = function(){
    const area = document.getElementById('rt-area');
    const html = area ? area.innerHTML : "";
    const td = new TurndownService({headingStyle:'atx', codeBlockStyle:'fenced'});
    const md = td.turndown(html || "");
    if (area) area.innerHTML = ""; // clear after grab
    return md;
  };
</script>
''')
            md_hidden = gr.Textbox(visible=False)
            files = gr.Files(label="Attach files (optional)", file_count="multiple")
            with gr.Row():
                send = gr.Button("Send", variant="primary")
                clear = gr.Button("Clear chat")

    # Wire: Send pulls editor -> md_hidden (JS), then calls respond()
    send.click(fn=None, inputs=None, outputs=md_hidden, js="() => window.__pullMarkdown()")         .then(fn=respond, inputs=[state, md_hidden, files], outputs=[chat, md_hidden])

    # Keep chat state in sync with Chatbot content
    def sync_state(h):
        return h
    chat.change(sync_state, inputs=chat, outputs=state)

    clear.click(lambda: ([], ""), outputs=[chat, md_hidden])

    # Warm greeting
    def welcome():
        return [{"role":"assistant","content":"Hi! Type in the rich editor, then press **Send**. I'll reply here."}], []
    demo.load(welcome, inputs=None, outputs=[chat, state])

if __name__ == "__main__":
    demo.queue().launch()

