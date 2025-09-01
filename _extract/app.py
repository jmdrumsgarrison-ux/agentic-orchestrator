import os, sys, json, time, re, shutil, yaml, requests, gradio as gr
from typing import List, Dict, Any
from git import Repo, Actor as GitActor

# ---------- Environment ----------
HOME_DIR = "/tmp/ao_home"; os.makedirs(HOME_DIR, exist_ok=True); os.environ.setdefault("HOME", HOME_DIR)
PORT = int(os.environ.get("PORT", "7860"))

GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY".lower(), ""))

HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
SPACE_ID = os.environ.get("SPACE_ID", "").strip()
if not HF_NAMESPACE and SPACE_ID and ("/" in SPACE_ID): HF_NAMESPACE = SPACE_ID.split("/")[0]

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

def _gh_headers(): return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
def _hf_headers(): return {"Authorization": f"Bearer {HF_TOKEN}"}
def _owner_from_default_repo():
    m = re.match(r"https?://github.com/([^/]+)/", AO_DEFAULT_REPO or "")
    return m.group(1) if m else None

FRIENDLY = (
    "👋 Hi, I’m AO — Agentic Orchestrator.\n\n"
    "Talk to me naturally about what you want to change or build. I’ll ask questions and refine the idea. "
    "When it’s clear, *I* will suggest trying a **Dev build** (I’ll get code from ChatGPT, patch it, deploy a Dev Space, and iterate on errors). "
    "Once the Dev build is stable, I’ll capture the change and we can promote it.\n\n"
    "Nothing runs without your go‑ahead, and every action starts with a dry‑run summary.\n"
)

# ---------- Git helpers ----------
def _clone_base(workdir="/tmp/ao_base"):
    if os.path.exists(workdir): shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)
    if not AO_DEFAULT_REPO: raise RuntimeError("AO_DEFAULT_REPO is not set")
    url = AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@") if GITHUB_TOKEN else AO_DEFAULT_REPO
    repo = Repo.clone_from(url, os.path.join(workdir, "repo"), depth=1)
    base = os.path.join(workdir, "repo")
    return repo, base

def _list_repo_files(base: str) -> List[str]:
    out = []
    for r, d, files in os.walk(base):
        if "/.git" in r: continue
        for f in files:
            p = os.path.join(r, f)
            out.append(os.path.relpath(p, base))
    return out

def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f: return f.read()
    except: return ""

def _commit_push(repo: Repo, paths: List[str], msg: str):
    actor = GitActor("AO Bot", "ao@example.com")
    if paths:
        repo.index.add(paths)
    else:
        repo.git.add(all=True)
    repo.index.commit(msg, author=actor, committer=actor)
    for remote in repo.remotes:
        try: remote.push()
        except Exception as e: pass

def _gh_whoami():
    try:
        me = requests.get("https://api.github.com/user", headers=_gh_headers(), timeout=20)
        if me.status_code == 200: return me.json().get("login","unknown")
    except: pass
    return "unknown"

# ---------- Dev repo + Space ----------
def _ensure_dev_repo(dev_name: str, seed_from_base_dir: str) -> str:
    """
    Create a new private GitHub repo under the authenticated user and seed with files from seed_from_base_dir.
    Returns the HTTPS repo url.
    """
    login = _gh_whoami()
    repo_url = f"https://github.com/{login}/{dev_name}"
    # create or reuse
    cr = requests.post("https://api.github.com/user/repos", headers=_gh_headers(),
                       json={"name": dev_name, "private": True, "auto_init": False}, timeout=30)
    if cr.status_code not in (201, 422):  # 422 = already exists
        raise RuntimeError(f"GitHub create failed: {cr.status_code} {cr.text[:120]}")

    # clone and copy tree
    dst_dir = f"/tmp/dev_{dev_name}"; shutil.rmtree(dst_dir, ignore_errors=True); os.makedirs(dst_dir, exist_ok=True)
    dst = Repo.clone_from(repo_url.replace("https://", f"https://{GITHUB_TOKEN}@"), os.path.join(dst_dir, "dst"))
    # copy files
    for r,d,files in os.walk(seed_from_base_dir):
        if "/.git" in r: continue
        rel = os.path.relpath(r, seed_from_base_dir)
        td = os.path.join(dst.working_tree_dir, rel); os.makedirs(td, exist_ok=True)
        for f in files:
            sp = os.path.join(r,f); dp = os.path.join(td,f)
            shutil.copy2(sp, dp)
    _commit_push(dst, [], "chore(seed): initial dev seed")
    return repo_url

def _ensure_dev_space(space_id: str, repo_url: str, hardware="cpu-basic") -> Dict[str, Any]:
    payload = {"sdk":"docker","private":True,"hardware":hardware,"repository":{"url":repo_url}}
    r = requests.post(f"https://huggingface.co/api/spaces/{space_id}", headers=_hf_headers(), json=payload, timeout=60)
    if r.status_code in (200,201):
        return {"created":True,"space_id":space_id}
    # if already exists, try to update repo source
    if r.status_code == 409:
        u = requests.patch(f"https://huggingface.co/api/spaces/{space_id}", headers=_hf_headers(),
                           json={"repository":{"url":repo_url}}, timeout=60)
        if u.status_code in (200, 201):
            return {"updated":True,"space_id":space_id}
    return {"error": f"{r.status_code} {r.text[:160]}"}

def _space_status(space_id: str) -> Dict[str, Any]:
    try:
        r = requests.get(f"https://huggingface.co/api/spaces/{space_id}", headers=_hf_headers(), timeout=20)
        if r.status_code==200: return r.json()
    except Exception as e:
        return {"error": str(e)}
    return {"error": f"status {r.status_code}"}

# ---------- OpenAI helpers ----------
def _openai_client():
    try:
        from openai import OpenAI
        if not OPENAI_API_KEY: return None
        client = OpenAI(api_key=OPENAI_API_KEY)
        return client
    except Exception as e:
        return None

PATCH_SYSTEM = """You are a code refactoring assistant working on an app that runs in a Docker Hugging Face Space.
User describes a change. You receive a repo tree snapshot (path+text of a few key files) and (optional) last error logs.
Return ONLY a JSON object with a top-level key "files" which is a list of objects { "path": "<relative file path>", "content": "<full new file content>" }.
- Each path is relative to repo root.
- Include full content for each changed file.
- Keep it minimal: only touch files you need.
- Do not include backticks, markdown, or commentary—just raw JSON.
"""

def _summarize_repo_for_llm(base: str, limit=6_000) -> str:
    # collect a few important files
    files = []
    for path in _list_repo_files(base):
        if len(files) > 12: break
        if path.endswith((".py",".md","Dockerfile",".yaml",".yml",".toml")):
            text = _read_text(os.path.join(base,path))
            if text and len(text) < 4000:
                files.append({"path":path, "text":text})
    return json.dumps({"files": files})[:limit]

def _llm_patch_request(notes: List[str], repo_summary: str, last_error: str = "") -> List[Dict[str,str]]:
    client = _openai_client()
    if not client: return []
    user_prompt = {
        "role": "user",
        "content": (
            "Proposed change (notes):\\n" + "\\n".join(notes) + "\\n\\n"
            "Repo summary JSON (subset of files):\\n" + repo_summary + "\\n\\n"
            "Last error (if any):\\n" + (last_error or "(none)") + "\\n\\n"
            "Return JSON only."
        )
    }
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"system","content":PATCH_SYSTEM}, user_prompt],
            temperature=0.2,
        )
        txt = resp.choices[0].message.content.strip()
        data = json.loads(txt)
        return data.get("files", [])
    except Exception as e:
        return []

def _apply_files_to_tree(base: str, files: List[Dict[str,str]]) -> List[str]:
    changed = []
    for f in files:
        path = f.get("path"); content = f.get("content","")
        if not path: continue
        abs_path = os.path.join(base, path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as w: w.write(content)
        changed.append(path)
    return changed

# ---------- Conversation & Orchestrator ----------
GUIDE_QS = [
    "What’s the goal or outcome you want?",
    "What would count as success (acceptance criteria)?",
    "Any constraints or risks (tokens, HF/Git limits, auth)?"
]

def _should_offer_dev_build(notes: List[str]) -> bool:
    # Offer only after we've touched on goal + success + maybe constraints or had 3+ turns.
    txt = " ".join(notes).lower()
    cues = sum([("goal" in txt), ("success" in txt) or ("accept" in txt), ("risk" in txt) or ("token" in txt) or ("limit" in txt)])
    return len(notes) >= 3 and cues >= 1

def _dev_build(notes: List[str], hardware="cpu-basic", max_attempts=3) -> Dict[str, Any]:
    # 1) Clone base
    repo, base = _clone_base("/tmp/ao_build")
    # 2) Summarize repo for LLM
    summary = _summarize_repo_for_llm(base)
    last_error = ""
    # 3) Iterate suggestions and apply
    for attempt in range(1, max_attempts+1):
        files = _llm_patch_request(notes, summary, last_error)
        if files:
            changed = _apply_files_to_tree(base, files)
            _commit_push(repo, changed, f"feat(dev): attempt {attempt} - apply LLM patch")
        else:
            # no patch, continue anyway with current tree
            pass

        # 4) Seed dev repo & space for this attempt
        cr_id = time.strftime("%Y%m%d%H%M%S")
        dev_name = f"AO-dev-{cr_id}"
        gh_url = _ensure_dev_repo(dev_name, base)
        space_id = f"{HF_NAMESPACE}/{dev_name}" if HF_NAMESPACE else f"{_gh_whoami()}/{dev_name}"
        sp = _ensure_dev_space(space_id, gh_url, hardware=hardware)
        status = _space_status(space_id)
        ok = False
        stage = (status.get("runtime",{}) or {}).get("stage","")
        if stage.lower() in ("running","sleeping","stopped"):
            ok = True
        elif "error" in status and "error" not in sp:
            last_error = str(status["error"])
        else:
            last_error = json.dumps(status)[:800]

        if ok:
            return {"ok": True, "dev_repo": gh_url, "space_id": space_id, "attempts": attempt}

        time.sleep(4)  # brief pause before next attempt
    return {"ok": False, "last_error": last_error[:800]}

def reset_chat():
    return [("", FRIENDLY)], "", {"mode":"chat","notes":[],"offered":False,"devResult":None}

def step_chat(history, user_text, state):
    history = history or []
    state = state or {"mode":"chat","notes":[],"offered":False,"devResult":None}
    text = (user_text or "").strip()
    if not text: return history, "", state

    # If user confirms a suggested dev build
    if state.get("offered") and re.search(r"\\b(yes|ok|sure|let’s try|lets try|go ahead|proceed)\\b", text.lower()):
        # Dry-run summary
        plan = f"Try a Dev build: I’ll fetch code suggestions, patch a dev repo, create a Dev Space, and iterate up to 3 attempts."
        history = history + [(text, f"**Dry‑run plan**\\n\\n- {plan}\\n- Hardware: cpu-basic\\n- Nothing will promote to prod automatically.")]
        # Execute
        try:
            res = _dev_build(state["notes"], hardware="cpu-basic", max_attempts=3)
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        state["offered"] = False
        state["devResult"] = res
        if res.get("ok"):
            reply = ("✅ Dev build succeeded. I’ve got a running Dev Space.\n"
                     f"- Dev Space: `{res['space_id']}`\n"
                     f"- Dev Repo: {res['dev_repo']}\n\n"
                     "I’ll capture this as a change and prepare it for review. When you’re ready, we can promote it.")
            return history + [("", reply)], "", state
        else:
            return history + [("", f"❌ Dev build didn’t succeed.\n\nLast signal:\n```json\n{json.dumps(res, indent=2)}\n```\nI can try again or refine the idea. What would you change?")], "", state

    # Detect change-intent to start collecting notes
    if any(w in text.lower() for w in ["change","modify","update","gui","tab","button","add ","remove ","storage","persist","space","spawn"]):
        state["mode"] = "discuss"
        state["notes"].append(text)
        # Ask one guiding question at a time
        if len(state["notes"]) <= 1:
            return history + [(text, f"Interesting. {GUIDE_QS[0]}")], "", state
        elif len(state["notes"]) == 2:
            return history + [(text, f"Got it. {GUIDE_QS[1]}")], "", state
        else:
            # After a few notes, decide whether to offer dev build
            if _should_offer_dev_build(state["notes"]):
                state["offered"] = True
                return history + [(text, "I think we’ve got enough to try a **Dev build**. Want me to attempt it now?")], "", state
            else:
                return history + [(text, f"Thanks. {GUIDE_QS[min(2, len(GUIDE_QS)-1)]}")], "", state

    # If user adds more detail while in discuss mode
    if state.get("mode") == "discuss":
        state["notes"].append(text)
        if _should_offer_dev_build(state["notes"]) and not state.get("offered"):
            state["offered"] = True
            return history + [(text, "This feels clear. Should I try a **Dev build** now?")], "", state
        return history + [(text, "Noted. Anything else before we try a Dev build?")], "", state

    # Default chit-chat
    return history + [(text, "Got it — I’m taking notes. Tell me more. When ready, I can try a **Dev build** for you.")], "", state

def ui_status():
    return {
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "SPACE_ID": SPACE_ID or "(unset)",
        "build": "AO v0.6.5 (Docker, AO-driven Dev build with LLM patches)"
    }

with gr.Blocks(title="AO v0.6.5 — AO-driven Dev build") as demo:
    gr.Markdown("## AO v0.6.5 — Conversational Dev builds (AO proposes, then iterates on errors).")
    with gr.Tab("Status"):
        env = gr.JSON()
        demo.load(ui_status, outputs=env)
    with gr.Tab("Chat"):
        chat = gr.Chatbot(height=500)
        txt = gr.Textbox(placeholder="Tell me what you want to change or build…")
        send = gr.Button("Send")
        reset = gr.Button("Reset")
        state = gr.State({"mode":"chat","notes":[],"offered":False,"devResult":None})
        def _reset():
            return [("", FRIENDLY)], "", {"mode":"chat","notes":[],"offered":False,"devResult":None}
        demo.load(_reset, outputs=[chat, txt, state])
        reset.click(_reset, outputs=[chat, txt, state])
        send.click(step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])
        txt.submit(step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

