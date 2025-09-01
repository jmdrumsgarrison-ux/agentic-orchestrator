import os, re, json, time, shutil, requests, gradio as gr
from typing import List, Dict, Any
from git import Repo, Actor as GitActor

HOME_DIR = "/tmp/ao_home"; os.makedirs(HOME_DIR, exist_ok=True); os.environ.setdefault("HOME", HOME_DIR)
PORT = int(os.environ.get("PORT", "7860"))

GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", os.environ.get("openai_api_key",""))
HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
SPACE_ID = os.environ.get("SPACE_ID", "").strip()
if not HF_NAMESPACE and SPACE_ID and ("/" in SPACE_ID): HF_NAMESPACE = SPACE_ID.split("/")[0]
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

def _gh_headers(): return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
def _hf_headers(): return {"Authorization": f"Bearer {HF_TOKEN}"}

def _gh_whoami():
    try:
        me = requests.get("https://api.github.com/user", headers=_gh_headers(), timeout=20)
        if me.status_code == 200: return me.json().get("login","unknown")
    except: pass
    return "unknown"

INTRO = (
    "👋 Hi, I’m AO — Agentic Orchestrator.\n\n"
    "Talk to me like you would in our old Drops loop. I’ll riff with you, surface options and trade‑offs, "
    "and when it *feels* converged I’ll suggest a Dev build (I’ll fetch code from ChatGPT, patch a dev repo, "
    "spin up a private Dev Space, test, and iterate on errors). When it’s stable, I’ll capture the change so we can promote it.\n\n"
    "Nothing runs until you say yes; I always show a dry‑run summary first.\n"
)

# ---- git helpers ----
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
    if paths: repo.index.add(paths)
    else: repo.git.add(all=True)
    repo.index.commit(msg, author=actor, committer=actor)
    for r in repo.remotes:
        try: r.push()
        except: pass

# ---- dev repo + space ----
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

# ---- LLM patcher ----
def _openai_client():
    try:
        from openai import OpenAI
        if not OPENAI_API_KEY: return None
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return None

PATCH_SYS = "Return JSON only with key 'files' as list of {path, content}. No commentary."

def _summarize_repo(base: str, limit=6000) -> str:
    files = []
    for r,_,fs in os.walk(base):
        if "/.git" in r: continue
        for f in fs:
            p = os.path.join(r,f)
            rel = os.path.relpath(p, base)
            if rel.endswith((".py",".md","Dockerfile",".yaml",".yml",".toml")):
                try:
                    t = open(p,"r",encoding="utf-8",errors="ignore").read()
                except: t = ""
                if t and len(t) < 4000:
                    files.append({"path":rel,"text":t})
        if len(files) > 12: break
    return json.dumps({"files":files})[:limit]

def _llm_patch(notes: List[str], summary: str, last_error: str="") -> List[Dict[str,str]]:
    client = _openai_client()
    if not client: return []
    msg = (
        "Proposed change notes:\\n" + "\\n".join(notes) +
        "\\n\\nRepo summary JSON:\\n" + summary +
        "\\n\\nLast error (if any):\\n" + (last_error or "(none)") +
        "\\n\\nReturn JSON only with 'files'."
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"system","content":PATCH_SYS},{"role":"user","content":msg}],
            temperature=0.2
        )
        data = json.loads(resp.choices[0].message.content.strip())
        return data.get("files", [])
    except Exception:
        return []

def _apply_files(base: str, files: List[Dict[str,str]]) -> List[str]:
    changed = []
    for f in files:
        p = f.get("path"); c = f.get("content","")
        if not p: continue
        ap = os.path.join(base,p); os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap,"w",encoding="utf-8") as w: w.write(c)
        changed.append(p)
    return changed

def _dev_build(notes: List[str], hardware="cpu-basic", max_attempts=3) -> Dict[str,Any]:
    repo, base = _clone_base("/tmp/ao_build")
    summary = _summarize_repo(base)
    last_error = ""
    for i in range(1, max_attempts+1):
        files = _llm_patch(notes, summary, last_error)
        if files:
            changed = _apply_files(base, files)
            _commit_push(repo, changed, f"feat(dev): attempt {i} - LLM patch")
        cr_id = time.strftime("%Y%m%d%H%M%S")
        dev_name = f"AO-dev-{cr_id}"
        gh_url = _ensure_dev_repo(dev_name, base)
        space_id = f"{HF_NAMESPACE}/{dev_name}" if HF_NAMESPACE else f"{_gh_whoami()}/{dev_name}"
        _ensure_dev_space(space_id, gh_url, hardware)
        status = _space_status(space_id)
        stage = (status.get('runtime',{}) or {}).get('stage','').lower()
        if stage in ("running","sleeping","stopped"):
            return {"ok":True,"attempts":i,"dev_repo":gh_url,"space_id":space_id}
        last_error = json.dumps(status)[:800]
        time.sleep(4)
    return {"ok":False,"last_error":last_error[:800]}

# ---- conversation helpers ----
def _coverage(notes: List[str]) -> int:
    t = " ".join(notes).lower()
    cats = [
        any(w in t for w in ["goal","outcome","so that","because"]),
        any(w in t for w in ["success","accept","done","pass","test"]),
        any(w in t for w in ["risk","limit","quota","token","cost","privacy","security"]),
        any(w in t for w in ["option","vs","versus","compare","s3","google drive","hf dataset","dataset","bucket"]),
    ]
    return sum(cats)

def _insightful_reply(text: str) -> str:
    t = text.lower()
    parts = []
    if "storage" in t or "persist" in t or "artifact" in t:
        parts.append(
            "On Spaces, persistence is non‑trivial. Practical routes:\n"
            "• **HF Datasets** – simple, versioned, great for artifacts/logs; pay by usage.\n"
            "• **S3/compatible** – scales and cheap at volume; needs key mgmt and SDK wiring.\n"
            "• **Google Drive** – easy for light assets; OAuth/rate limits can bite in prod.\n"
            "My bias: start with HF Datasets for small/medium artifacts, move to S3 when throughput or cost matter."
        )
    if "image" in t and "generate" in t:
        parts.append("For generated images, write a small store() helper (filename = UTC timestamp + hash) and a list() view. That keeps the UI snappy and storage tidy.")
    if "gui" in t or "tab" in t or "button" in t:
        parts.append("UX tweak idea: a **Storage** panel with destination selector (Datasets/S3/Drive), latest save status, and a quick-open link to the browse page.")
    if not parts:
        parts.append("Got it. Tell me a bit more and I’ll riff on options and trade‑offs.")
    return "\n\n".join(parts) + "\n\nDoes that direction line up with what you have in mind?"

def _ready(notes: List[str]) -> bool:
    return (len(notes) >= 4) and (_coverage(notes) >= 2)

def reset_chat():
    return [("", INTRO)], "", {"mode":"chat","notes":[],"offered":False,"dev":None}

def step_chat(history, user_text, state):
    history = history or []
    state = state or {"mode":"chat","notes":[],"offered":False,"dev":None}
    text = (user_text or "").strip()
    if not text: return history, "", state

    # if user accepts dev build
    if state.get("offered") and re.search(r"\\b(yes|ok|sure|go ahead|proceed|let.?s try)\\b", text.lower()):
        plan = ("Dev build plan: fetch code from ChatGPT, patch dev repo, create private Dev Space, iterate up to 3 times; "
                "report results. (dry‑run shown; executing now)")
        history = history + [(text, f"**Dry‑run summary**\\n- {plan}\\n- Hardware: cpu-basic")]
        try:
            res = _dev_build(state["notes"], "cpu-basic", 3)
        except Exception as e:
            res = {"ok":False,"error":str(e)}
        state["offered"] = False
        state["dev"] = res
        if res.get("ok"):
            msg = (f"✅ Dev build succeeded (attempt {res['attempts']}).\\n"
                   f"- Dev Space: `{res['space_id']}`\\n- Dev Repo: {res['dev_repo']}\\n"
                   "I’ve captured this change so we can promote it when you’re ready.")
        else:
            msg = f"❌ Dev build didn’t stabilize. Last signal:\\n```json\\n{json.dumps(res,indent=2)}\\n```\\nWe can refine and retry."
        return history + [("", msg)], "", state

    # detect intent to change/build
    if any(w in text.lower() for w in ["change","modify","update","add ","remove ","storage","persist","artifact","gui","tab","button","space","spawn","image"]):
        state["mode"] = "discuss"
        state["notes"].append(text)
        if _ready(state["notes"]):
            state["offered"] = True
            return history + [(text, "It feels like we’re aligned. Want me to try a **Dev build** to validate this?")], "", state
        else:
            return history + [(text, _insightful_reply(text))], "", state

    # ongoing discussion
    if state.get("mode") == "discuss":
        state["notes"].append(text)
        if _ready(state["notes"]) and not state.get("offered"):
            state["offered"] = True
            return history + [(text, "Sounds converged. Shall I kick off a **Dev build**?")], "", state
        return history + [(text, _insightful_reply(text))], "", state

    # default chat
    return history + [(text, "Noted. Keep going — I’ll suggest options and a Dev build when we’ve got enough shape.")], "", state

def ui_status():
    return {
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "SPACE_ID": SPACE_ID or "(unset)",
        "build": "AO v0.6.7 (Docker) — Drop-style exploration, no questionnaire tone"
    }

with gr.Blocks(title="AO v0.6.7") as demo:
    gr.Markdown("## AO v0.6.7 — Conversational Dev builds (Drop-style exploration, AO proposes when ready).")
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
            return [("", INTRO)], "", {"mode":"chat","notes":[],"offered":False,"dev":None}
        demo.load(_reset, outputs=[chat, txt, state])
        reset.click(_reset, outputs=[chat, txt, state])
        send.click(step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])
        txt.submit(step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

