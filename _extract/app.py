
import os
import gradio as gr

APP_VERSION = "v0.8.7 — GPT-5 (text), Markdown editor, file uploads, version banner"
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5")
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "").strip()

# --- Dummy LLM responder (echo/format) ---
# Keeps the app working even if no API key is configured.
def llm_reply(prompt: str) -> str:
    if not prompt:
        return "Please provide a message."
    # If no key, just reflect the prompt in a friendly way.
    if not OPENAI_API_KEY:
        return f"(local preview — no OPENAI_API_KEY set)\n\nYou said:\n\n{prompt}"
    # Lightweight fallback to prevent runtime import errors on spaces without internet
    # Replace with real OpenAI client usage in your environment if desired.
    return f"(stubbed) Using model **{MODEL_NAME}** with your message:\n\n{prompt}"

# --- Chat logic ---
def chat_send(user_message, history, editor_md, files):
    # Prefer the explicit message; if empty, fallback to the editor content
    content = (user_message or "").strip() or (editor_md or "").strip()
    if not content and files:
        content = "Files uploaded: " + ", ".join([getattr(f, 'name', 'file') for f in files])
    if not content:
        return history, ""

    reply = llm_reply(content)
    history = history or []
    history.append([content, reply])
    return history, ""

def use_editor_content(editor_md):
    # Push the editor content into the message box
    return (editor_md or "").strip()

def update_preview(md_text):
    return gr.Markdown.update(value=(md_text or "").strip())

with gr.Blocks(fill_height=True, theme=gr.themes.Soft()) as demo:
    # Banner
    gr.Markdown(f"### Agentive Orchestrator — {APP_VERSION}\nModel: `{MODEL_NAME}`")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=420, label="Chat")
            with gr.Row():
                msg = gr.Textbox(label="Message", placeholder="Type message… (or use the right-side editor and click 'Use editor content')", scale=4)
                send = gr.Button("Send", variant="primary", scale=1)
            uploads = gr.Files(label="Upload files (optional)", file_count="multiple")

        with gr.Column(scale=1):
            gr.Markdown("**Markdown editor** (use toolbar below editor for bullets, headings etc. in your own editor then paste — this box supports Markdown with live preview)")
            editor = gr.Textbox(label="Markdown", lines=14, placeholder="Write rich text here in Markdown…")
            preview = gr.Markdown("*(live preview)*")
            use_btn = gr.Button("Use editor content → message", variant="secondary")

    # Wiring
    send.click(chat_send, [msg, chatbot, editor, uploads], [chatbot, msg])
    use_btn.click(use_editor_content, [editor], [msg])
    editor.change(update_preview, [editor], [preview])

# For Spaces
if __name__ == "__main__":
    demo.launch()

