import os
import gradio as gr

# --- Config ---
APP_VERSION = "AO v0.8.2 — GPT‑5 chat + separate uploads (safe)"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are AO (Agentic Orchestrator). Be concise, helpful, and honest. "
    "If the user uploads files, acknowledge them but do not assume content unless parsed."
)

# We keep text chat and uploads on separate flows to avoid Gradio treating text as a file.
# This prevents the 'InvalidPathError ... because it was not uploaded by a user' error.

# --- OpenAI client (lazy import to allow space to start without key) ---
_client = None
def _get_client():
    global _client
    if _client is None:
        try:
            from openai import OpenAI
            _client = OpenAI()
        except Exception as e:
            _client = e  # stash exception for later surfacing
    return _client

def _call_openai(messages):
    client = _get_client()
    if isinstance(client, Exception):
        # Surface a friendly error if OpenAI SDK isn't ready
        return f"(OpenAI client not initialized: {client})"
    try:
        # Use Chat Completions for broad compatibility
        res = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"(OpenAI error: {e})"

# --- Handlers ---
def handle_chat(user_message, history, sys_prompt):
    if not user_message.strip():
        return "", history

    # Convert Gradio history [(user, bot), ...] to OpenAI messages
    msgs = [{"role": "system", "content": sys_prompt or SYSTEM_PROMPT}]
    for u, b in history:
        if u:
            msgs.append({"role": "user", "content": u})
        if b:
            msgs.append({"role": "assistant", "content": b})
    msgs.append({"role": "user", "content": user_message})

    reply = _call_openai(msgs)
    history = history + [(user_message, reply)]
    return "", history

def handle_files(files):
    # Return a list of file paths for preview in the Gallery.
    # We do not mix this with the chat submission pipeline.
    if not files:
        return []
    # Gradio provides temporary paths; just bounce them back for preview.
    paths = [f.name if hasattr(f, "name") else f for f in files]
    return paths

def clear_history():
    return []

with gr.Blocks(fill_height=True, theme=gr.themes.Soft()) as demo:
    gr.Markdown(f"### {APP_VERSION}  
"
                f"*Text chat uses **{OPENAI_MODEL}** (set `OPENAI_MODEL` env to override).*")

    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(height=520, show_copy_button=True)
            with gr.Row():
                msg = gr.Textbox(placeholder="Type here…", scale=8)
                send = gr.Button("Send", variant="primary", scale=1)
            with gr.Row():
                clear = gr.Button("Clear chat")
        with gr.Column(scale=2):
            gr.Markdown("**Optional uploads (shown below):**

"
                        "- Drag & drop images/docs here to preview.
"
                        "- Chat logic is separate, so uploads won't interfere.")
            uploads = gr.Files(label="Upload files (optional)", file_count="multiple")
            gallery = gr.Gallery(label="Uploads preview (this session)",
                                 height=350, columns=6, preview=True)

    # Wire events
    msg.submit(handle_chat, [msg, chatbot, gr.State(SYSTEM_PROMPT)], [msg, chatbot])
    send.click(handle_chat, [msg, chatbot, gr.State(SYSTEM_PROMPT)], [msg, chatbot])
    clear.click(clear_history, None, chatbot)

    uploads.change(handle_files, uploads, gallery)

if __name__ == "__main__":
    # Hugging Face Spaces honors PORT; fallback for local runs.
    port = int(os.environ.get("PORT", "7860"))
    demo.launch(server_name="0.0.0.0", server_port=port)
