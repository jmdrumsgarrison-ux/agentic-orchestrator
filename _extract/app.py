import os, io, shutil, zipfile, time, re, gradio as gr
from typing import List, Dict, Any

PORT = int(os.environ.get("PORT","7860"))
HOME = "/tmp/ao_home"; os.makedirs(HOME, exist_ok=True)

BANNER = """\
# AO v0.7.2 — Drops (semantic versioning)

Same Drops workflow, but **no Drop numbers**. You set the semantic **version** (e.g., `v0.7.2`), and the server packages:
- `AO_<version>.zip`
- `DROP_NOTES.md` and `README.md` carrying the version
- All uploaded attachments under `/assets`

Nothing executes automatically. This is the same “old way” loop, hosted in the server.
"""

SEMVER_RE = re.compile(r"^v?(\\d+)\\.(\\d+)\\.(\\d+)$")

def _ts(): return time.strftime("%Y-%m-%d %H:%M:%S")

def _init_state():
    return {
        "chat": [],
        "attachments": [],
        "version": "v0.7.2",
        "proposed": False,
        "confirmed": False,
        "title": "",
        "summary": "",
    }

def reset_all():
    st = _init_state()
    welcome = "Drops mode (semver). Describe what you want. When aligned, say **propose a Drop**. Upload files to include. Say **yes** to build."
    return [("", welcome)], "", st, st["version"], "", ""

def _append(history, you=None, me=None):
    return history + [(you or "", me or "")]

def chat_step(history, user_text, st):
    history = history or []
    st = st or _init_state()
    msg = (user_text or "").strip()
    if not msg: return history, "", st
    lower = msg.lower()

    # confirm build
    if st.get("proposed") and any(w in lower for w in ["yes","ship it","do it","build it","go ahead","proceed"]):
        st["confirmed"] = True
        reply = f"Great — I’ll package **AO_{st['version']}** now. You’ll get a zip you can drop into Spaces."
        return _append(history, msg, reply), "", st

    # propose
    if "propose a drop" in lower or "prepare a drop" in lower or "roll the next drop" in lower:
        st["proposed"] = True
        title = st["title"] or f"AO {st['version']}"
        reply = (f"Proposing **{title}** ({st['version']}). "
                 f"If that looks right, say **yes** to build. You can also set a title/summary first.")
        return _append(history, msg, reply), "", st

    # normal talk
    canned = "Got it. If we’re aligned, say **propose a Drop** and I’ll stage it. Upload files anytime; they’ll be included."
    return _append(history, msg, canned), "", st

def set_meta(version, title, summary, st):
    st = st or _init_state()
    v = (version or "").strip()
    if v and SEMVER_RE.match(v): st["version"] = v if v.startswith("v") else f"v{v}"
    st["title"] = title or ""
    st["summary"] = summary or ""
    return st

def receive_files(files, st):
    st = st or _init_state()
    updir = os.path.join(HOME, "uploads"); os.makedirs(updir, exist_ok=True)
    added = []
    if files:
        for f in files:
            if not f: continue
            dst = os.path.join(updir, os.path.basename(f.name))
            shutil.copy2(f.name, dst)
            st["attachments"].append({"name": os.path.basename(dst), "path": dst, "size": os.path.getsize(dst)})
            added.append(os.path.basename(dst))
    return ("Attached: " + (", ".join(added) if added else "(none)")), st

def _write(history, st, outroot):
    with open(os.path.join(outroot, "DROP_NOTES.md"), "w", encoding="utf-8") as f:
        f.write(f"# AO {st['version']} — {st['title'] or 'Untitled'}\\n\\n")
        if st.get("summary"): f.write(st["summary"] + "\\n\\n")
        f.write("## Conversation\\n")
        for u,a in history or []:
            if u: f.write(f"- **You:** {u}\\n")
            if a: f.write(f"  - **AO:** {a}\\n")
        if st["attachments"]:
            f.write("\\n## Attachments\\n")
            for att in st["attachments"]:
                f.write(f"- {att['name']} ({att['size']} bytes)\\n")

    with open(os.path.join(outroot, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"AO {st['version']} — packaged by AO.\\n\\nUnzip into your Space root.\\n")

    assets = os.path.join(outroot, "assets"); os.makedirs(assets, exist_ok=True)
    for att in st["attachments"]:
        shutil.copy2(att["path"], os.path.join(assets, att["name"]))

def build_zip(history, st):
    st = st or _init_state()
    if not st.get("confirmed"):
        return None, "Say **yes** to confirm building this version."
    outroot = os.path.join(HOME, "out"); shutil.rmtree(outroot, ignore_errors=True); os.makedirs(outroot, exist_ok=True)
    _write(history, st, outroot)
    safe = st["version"].replace("/", "_")
    zip_path = os.path.join(HOME, f"AO_{safe}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r,_,fs in os.walk(outroot):
            for fn in fs:
                ap = os.path.join(r, fn)
                z.write(ap, arcname=os.path.relpath(ap, outroot))
    st["confirmed"] = False
    st["proposed"] = False
    return zip_path, f"Built AO_{safe}.zip. Remember to bump the version for the next Drop."

with gr.Blocks(title="AO v0.7.2 — Drops (semver)") as demo:
    gr.Markdown(BANNER)
    with gr.Row():
        with gr.Column(scale=2):
            chat = gr.Chatbot(height=480, label="Chat")
            user = gr.Textbox(placeholder="Say anything… e.g., 'Propose a Drop', 'Here are logs', 'Yes'")
            send = gr.Button("Send")
        with gr.Column(scale=1):
            gr.Markdown("### Versioned Release")
            version = gr.Textbox(value="v0.7.2", label="Version (semver: vX.Y.Z)")
            title = gr.Textbox(label="Title (optional)")
            summary = gr.Textbox(lines=6, label="Summary / release notes (optional)")
            files = gr.File(label="Upload attachments (multiple)", file_count="multiple")
            attach_status = gr.Textbox(label="Attachment status", interactive=False, value="Ready.")
            build = gr.Button("Build AO_<version>.zip")
            out_zip = gr.File(label="Download AO_<version>.zip")
            out_msg = gr.Markdown()

    state = gr.State(_init_state())

    def _boot():
        return [("", "Welcome to AO v0.7.2 — Drops (semver). Same workflow, now versioned.")], "", _init_state(), "v0.7.2", "", ""
    demo.load(_boot, outputs=[chat, user, state, version, title, summary])

    send.click(chat_step, inputs=[chat, user, state], outputs=[chat, user, state])
    version.change(set_meta, inputs=[version, title, summary, state], outputs=state)
    title.change(set_meta, inputs=[version, title, summary, state], outputs=state)
    summary.change(set_meta, inputs=[version, title, summary, state], outputs=state)
    files.upload(receive_files, inputs=[files, state], outputs=[attach_status, state])
    build.click(build_zip, inputs=[chat, state], outputs=[out_zip, out_msg])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
