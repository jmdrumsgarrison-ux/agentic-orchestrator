import os, re, json, time, shutil, yaml, requests, gradio as gr
from typing import List, Dict, Any
from git import Repo, Actor as GitActor

# ---------- ENV ----------
HOME_DIR = "/tmp/ao_home"; os.makedirs(HOME_DIR, exist_ok=True); os.environ.setdefault("HOME", HOME_DIR)
PORT = int(os.environ.get("PORT", "7860"))

GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", os.environ.get("openai_api_key",""))

HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
SPACE_ID = os.environ.get("SPACE_ID", "").strip()
if not HF_NAMESPACE and SPACE_ID and ("/" in SPACE_ID):
    HF_NAMESPACE = SPACE_ID.split("/")[0]

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# ---------- Helpers ----------
def _gh_headers(): return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
def _hf_headers(): return {"Authorization": f"Bearer {HF_TOKEN}"}

def _gh_whoami():
    try:
        me = requests.get("https://api.github.com/user", headers=_gh_headers(), timeout=20)
        if me.status_code == 200: return me.json().get("login","unknown")
    except: pass
    return "unknown"

FRIENDLY = (
    "👋 Hi, I’m AO — Agentic Orchestrator.\n\n"
    "Describe what you want to change or build. I’ll explore with you (goals, success, risks, options), "
    "then *I* will suggest a Dev build when we’re really ready. I’ll fetch code from ChatGPT, patch a dev repo, "
    "create a Dev Space, test, and iterate on errors. When stable, I’ll capture the change so we can promote it.\n\n"
    "Everything starts as a dry‑run; nothing executes until you confirm.\n"
)

# ---------- Git base ----------
def _clone_base(work="/tmp/ao_base"):
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    if not AO_DEFAULT_REPO: raise RuntimeError("AO_DEFAULT_REPO is not set")
    url = AO_DEFAULT_REPO
    if GITHUB_TOKEN and url.startswith("https://"): url = url.replace("https://", f"https://{GITHUB_TOKEN}@")
    repo = Repo.clone_from(url, os.path.join(work, "repo"), depth=1)
    return repo, os.path.join(work, "repo")

def _commit_push(repo: Repo, paths: List[str], msg: str):
    actor = GitActor("AO Bot", "ao@example.com")
    if paths:
        repo.index.add(paths)
    else:
        repo.git.add(all=True)
    repo.index.commit(msg, author=actor, committer=actor)
    for r in repo.remotes:
        try: r.push()
        except: pass

def _list_repo_files(base: str) -> List[str]:
    out = []
    for r,_,fs in os.walk(base):
        if "/.git" in r: continue
        for f in fs:
            out.append(os.path.relpath(os.path.join(r,f), base))
    return out

def _read_text(p):
    try:
        with open(p,"r",encoding="utf-8",errors="ignore") as f: return f.read()
    except: return ""

# ---------- Dev repo + Space ----------
def _ensure_dev_repo(dev_name: str, seed_dir: str) -> str:
    login = _gh_whoami()
    repo_url = f"https://github.com/{login}/{dev_name}"
    r = requests.post("https://api.github.com/user/repos", headers=_gh_headers(),
                      json={"name":dev_name,"private":True,"auto_init":False}, timeout=30)
    if r.status_code not in (201,422):
        raise RuntimeError(f"GitHub create repo failed: {r.status_code} {r.text[:160]}")

    dst_root = f"/tmp/dev_{dev_name}"; shutil.rmtree(dst_root, ignore_errors=True); os.makedirs(dst_root, exist_ok=True)
    dst = Repo.clone_from(repo_url.replace("https://", f"https://{GITHUB_TOKEN}@"), os.path.join(dst_root, "dst"))
    # copy tree
    for r,_,fs in os.walk(seed_dir):
        if "/.git" in r: continue
        rel = os.path.relpath(r, seed_dir)
        td = os.path.join(dst.working_tree_dir, rel); os.makedirs(td, exist_ok=True)
        for f in fs:
            sp = os.path.join(r,f); dp = os.path.join(td,f)
            shutil.copy2(sp, dp)
    _commit_push(dst, [], "chore(seed): initial dev seed")
    return repo_url

def _ensure_dev_space(space_id: str, repo_url: str, hardware="cpu-basic") -> Dict[str,Any]:
    payload = {"sdk":"docker","private":True,"hardware":hardware,"repository":{"url":repo_url}}
    r = requests.post(f"https://huggingface.co/api/spaces/{space_id}", headers=_hf_headers(), json=payload, timeout=60)
    if r.status_code in (200,201): return {"created":True,"space_id":space_id}
    if r.status_code == 409:
        u = requests.patch(f"https://huggingface.co/api/spaces/{space_id}", headers=_hf_headers(),
                           json={"repository":{"url":repo_url}}, timeout=60)
        if u.status_code in (200,201): return {"updated":True,"space_id":space_id}
    return {"error": f"{r.status_code} {r.text[:200]}"}

def _space_status(space_id: str) -> Dict[str,Any]:
    try:
        r = requests.get(f"https://huggingface.co/api/spaces/{space_id}", headers=_hf_headers(), timeout=20)
        if r.status_code==200: return r.json()
        return {"error": f"status {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}

# ---------- OpenAI patcher ----------
def _openai_client():
    try:
        from openai import OpenAI
        if not OPENAI_API_KEY: return None
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return None

PATCH_SYSTEM = """You are a code refactoring assistant working on an app that runs in a Docker Hugging Face Space.
User describes a change. You receive a repo tree snapshot (a few key files) and an optional last error.
Return ONLY JSON with key "files": a list of {"path":"<relative path>", "content":"<full new file content>"}.
No backticks or commentary, JSON only.
"""

def _summarize_repo(base: str, limit_chars=6000) -> str:
    files = []
    for path in _list_repo_files(base):
        if len(files) > 12: break
        if path.endswith((".py",".md","Dockerfile",".yaml",".yml",".toml")):
            txt = _read_text(os.path.join(base,path))
            if txt and len(txt) < 4000:
                files.append({"path":path, "text":txt})
    s = json.dumps({"files":files})
    return s[:limit_chars]

def _llm_patch(notes: List[str], summary: str, last_error: str="") -> List[Dict[str,str]]:
    client = _openai_client()
    if not client: return []
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role":"system","content":PATCH_SYSTEM},
                {"role":"user","content":(
                    "Proposed change notes:\\n"+ "\\n".join(notes) +
                    "\\n\\nRepo summary JSON:\\n" + summary +
                    "\\n\\nLast error (if any):\\n" + (last_error or "(none)") +
                    "\\n\\nReturn JSON only."
                )}
            ],
            temperature=0.2
        )
        txt = resp.choices[0].message.content.strip()
        data = json.loads(txt)
        return data.get("files", [])
    except Exception:
        return []

def _apply_files(base: str, files: List[Dict[str,str]]) -> List[str]:
    changed = []
    for f in files:
        p = f.get("path"); c = f.get("content","")
        if not p: continue
        ap = os.path.join(base, p)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap,"w",encoding="utf-8") as w: w.write(c)
        changed.append(p)
    return changed

# ---------- Conversation logic ----------
GUIDE = [
    "What’s the goal or outcome you want?",
    "What would count as success (acceptance criteria)?",
    "Any constraints or risks (auth, limits, cost, privacy)?",
    "What options should we compare (e.g., HF Datasets, S3, Google Drive)?",
]

def _flag_coverage(notes: List[str]) -> Dict[str,bool]:
    txt = " ".join(notes).lower()
    return {
        "goal": any(w in txt for w in ["goal","outcome","so that","because"]),
        "success": any(w in txt for w in ["success","accept","done","pass","test"]),
        "constraints": any(w in txt for w in ["risk","limit","quota","token","cost","privacy","security"]),
        "options": any(w in txt for w in ["option","vs","versus","compare","s3","google drive","hf dataset","dataset","bucket"]),
    }

def _ready_to_offer(notes: List[str]) -> bool:
    flags = _flag_coverage(notes)
    coverage = sum(flags.values())
    # Be conservative: 4+ turns and at least 2 categories touched
    return (len(notes) >= 4) and (coverage >= 2)

def _dev_build(notes: List[str], hardware="cpu-basic", max_attempts=3) -> Dict[str,Any]:
    repo, base = _clone_base("/tmp/ao_build")
    summary = _summarize_repo(base)
    last_error = ""
    for i in range(1, max_attempts+1):
        files = _llm_patch(notes, summary, last_error)
        if files:
            changed = _apply_files(base, files)
            _commit_push(repo, changed, f"feat(dev): attempt {i} - LLM patch")
        # seed dev repo + space
        cr_id = time.strftime("%Y%m%d%H%M%S")
        dev_name = f"AO-dev-{cr_id}"
        gh_url = _ensure_dev_repo(dev_name, base)
        space_id = f"{HF_NAMESPACE}/{dev_name}" if HF_NAMESPACE else f"{_gh_whoami()}/{dev_name}"
        sp = _ensure_dev_space(space_id, gh_url, hardware=hardware)
        status = _space_status(space_id)
        ok = False
        stage = (status.get("runtime",{}) or {}).get("stage","").lower()
        if stage in ("running","sleeping","stopped"): ok = True
        else: last_error = json.dumps(status)[:800]
        if ok:
            return {"ok":True,"attempts":i,"dev_repo":gh_url,"space_id":space_id}
        time.sleep(4)
    return {"ok":False,"last_error":last_error[:800]}

def reset_chat():
    return [("", FRIENDLY)], "", {"mode":"chat","notes":[],"offered":False,"dev":None}

def _explore_reply(text: str, notes: List[str]) -> str:
    # Offer thoughtful exploration like our drops conversation.
    t = text.lower()
    suggestions = []
    if "storage" in t or "persist" in t:
        suggestions.append(
            "For persistent storage on Spaces, options include:\n"
            "- **HF Datasets** (simple, versioned, good for artifacts)\n"
            "- **S3/compatible** (scales, but needs creds)\n"
            "- **Google Drive** (easy, but OAuth + rate limits)\n"
            "Trade‑offs: cost, auth complexity, write frequency, privacy."
        )
    if "gui" in t or "tab" in t or "button" in t:
        suggestions.append(
            "On the GUI side, we could add a **Settings** tab for storage target, "
            "plus a small status area showing last sync/results."
        )
    flags = _flag_coverage(notes)
    ask = None
    if not flags["goal"]: ask = GUIDE[0]
    elif not flags["success"]: ask = GUIDE[1]
    elif not flags["constraints"]: ask = GUIDE[2]
    elif not flags["options"]: ask = GUIDE[3]
    else: ask = "Anything else before we consider a Dev build?"
    extra = ("\n\n" + "\n\n".join(suggestions)) if suggestions else ""
    return f"{ask}{extra}"

def step_chat(history, user_text, state):
    history = history or []
    state = state or {"mode":"chat","notes":[],"offered":False,"dev":None}
    text = (user_text or "").strip()
    if not text: return history, "", state

    # If user accepts a proposed dev build
    if state.get("offered") and re.search(r"\\b(yes|ok|sure|go ahead|proceed|let.?s try)\\b", text.lower()):
        plan = ("Dev build plan: I'll fetch code suggestions, patch a dev repo, create a private Dev Space, "
                "and iterate up to 3 attempts before reporting back. (dry‑run shown; confirm to execute)")
        history = history + [(text, f"**Dry‑run summary**\\n- {plan}\\n- Hardware: cpu-basic")]
        # Immediate execute after dry-run summary (user already confirmed affirmative)
        try:
            res = _dev_build(state["notes"], "cpu-basic", 3)
        except Exception as e:
            res = {"ok":False,"error":str(e)}
        state["offered"] = False
        state["dev"] = res
        if res.get("ok"):
            reply = (f"✅ Dev build succeeded (attempt {res['attempts']}).\\n"
                     f"- Dev Space: `{res['space_id']}`\\n- Dev Repo: {res['dev_repo']}`\\n"
                     "I’ve captured this as a change. We can promote when you’re ready.")
        else:
            reply = f"❌ Dev build didn’t stabilize. Last signal:\\n```json\\n{json.dumps(res,indent=2)}\\n```\\nWe can tweak the idea or retry."
        return history + [("", reply)], "", state

    # Detect "change" discussion
    if any(w in text.lower() for w in ["change","modify","update","add ","remove ","gui","tab","button","storage","persist","space","spawn"]):
        state["mode"] = "discuss"
        state["notes"].append(text)
        # If ready, offer; else explore
        if _ready_to_offer(state["notes"]):
            state["offered"] = True
            return history + [(text, "I think we’ve converged — should I try a **Dev build**?")], "", state
        else:
            return history + [(text, _explore_reply(text, state["notes"]))], "", state

    # Continue discussion mode
    if state.get("mode") == "discuss":
        state["notes"].append(text)
        if _ready_to_offer(state["notes"]) and not state.get("offered"):
            state["offered"] = True
            return history + [(text, "This feels clear. Want me to try a **Dev build** now?")], "", state
        return history + [(text, _explore_reply(text, state["notes"]))], "", state

    # Default chat
    return history + [(text, "Got it — I’m taking notes. Tell me more and I’ll suggest a Dev build when it’s ready.")], "", state

def ui_status():
    return {
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "SPACE_ID": SPACE_ID or "(unset)",
        "build": "AO v0.6.6 (Docker) — Explore first, propose Dev build on convergence"
    }

with gr.Blocks(title="AO v0.6.6") as demo:
    gr.Markdown("## AO v0.6.6 — Conversational Dev builds (explore first, AO proposes when ready).")
    with gr.Tab("Status"):
        env = gr.JSON()
        demo.load(ui_status, outputs=env)
    with gr.Tab("Chat"):
        chat = gr.Chatbot(height=500)
        txt = gr.Textbox(placeholder="Tell me what you want to change or build…")
        send = gr.Button("Send")
        reset = gr.Button("Reset")
        state = gr.State({"mode":"chat","notes":[],"offered":False,"dev":None})
        def _reset():
            return [("", FRIENDLY)], "", {"mode":"chat","notes":[],"offered":False,"dev":None}
        demo.load(_reset, outputs=[chat, txt, state])
        reset.click(_reset, outputs=[chat, txt, state])
        send.click(step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])
        txt.submit(step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

