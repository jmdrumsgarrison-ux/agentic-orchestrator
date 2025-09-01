
import os
import gradio as gr
from datetime import datetime

# OpenAI client (optional at runtime)
try:
    from openai import OpenAI
    _openai_available = True
except Exception:
    _openai_available = False

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5").strip() or "gpt-5"
BANNER_VER   = "AO v0.8.4 — GPT-5 + uploads + banner"
WELCOME      = "Hi! Drop text, rich text, and files. I’ll reply using your OpenAI key."

def _call_openai(messages):
    """
    Calls OpenAI if available and key present.
    Falls back to a simple echo-style response to avoid hard crashes.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if _openai_available and api_key:
        try:
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.2,
            )
            return resp.choices[0].message.content or "(empty response)"
        except Exception as e:
            return f"(OpenAI call failed: {e})"
    else:
        return "(No OPENAI_API_KEY set) " + (messages[-1].get("content") if messages else "")

def on_send(chat_state, text_input, rich_text, files):
    # Prefer the RichText content if present, else the plain textbox
    content = (rich_text or "").strip()
    if not content:
        content = (text_input or "").strip()

    if not content and not files:
        return gr.update(), chat_state, ""

    # Build OpenAI-style messages
    if not isinstance(chat_state, list):
        chat_state = []

    user_parts = [{"type": "text", "text": content}] if content else []
    # Attach file references (as text list) — preview is handled separately by Gallery
    if files:
        file_list = "\n".join([os.path.basename(f) for f in files])
        user_parts.append({"type": "text", "text": f"[Attached files]\\n{file_list}"})
    chat_state.append({"role": "user", "content": user_parts})

    # Call model
    reply = _call_openai(chat_state)
    chat_state.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})

    # Clear inputs after send
    return chat_state, chat_state, "", ""

with gr.Blocks(theme="soft", fill_height=True) as demo:
    with gr.Row():
        gr.Markdown(f"### {BANNER_VER}  \nModel: `{OPENAI_MODEL}`  \nTime: {datetime.utcnow().isoformat()}Z")

    with gr.Row(equal_height=True):
        with gr.Column(scale=2):
            chat = gr.Chatbot(type="messages", height=420, label="Chat")
            chat_state = gr.State([])

            text = gr.Textbox(
                label="Message (multiline)",
                placeholder="Shift+Enter for newline, Enter to send",
                lines=6
            )

            with gr.Group():
                gr.Markdown("**Rich text (Quill)** — toolbar for bold/italics/lists; content is sent as Markdown.")
                rich = gr.RichText(placeholder="Write rich text here...", show_copy_button=True)

            files = gr.File(label="Upload files (multiple)", file_count="multiple", type="filepath")
            gallery = gr.Gallery(label="Preview", height=160)

            def show_previews(uploaded):
                return uploaded or []

            files.change(show_previews, inputs=files, outputs=gallery)

            send_btn = gr.Button("Send", variant="primary")
            send_btn.click(
                on_send,
                inputs=[chat_state, text, rich, files],
                outputs=[chat, chat_state, text, rich],
            )

        with gr.Column():
            gr.Markdown("> **Tips**  \n> • Use the rich editor for bullets/links.  \n> • Upload screenshots/logs below.  \n> • Set `OPENAI_API_KEY` (and optional `OPENAI_MODEL`) in your Space secrets.")

    # Warm welcome
    gr.on(
        triggers=None,
        fn=lambda: ([{"role": "assistant", "content": [{"type": "text", "text": WELCOME}]}], [{"role":"assistant","content":[{"type":"text","text":WELCOME}]}], "", ""),
        inputs=None,
        outputs=[chat, chat_state, text, rich]
    )

if __name__ == "__main__":
    demo.launch()
