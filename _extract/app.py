import os, sys, json, time, re, shutil, yaml
import gradio as gr

# --- Hardening ---
HOME_DIR = "/tmp/ao_home"
os.makedirs(HOME_DIR, exist_ok=True)
os.environ.setdefault("HOME", HOME_DIR)
os.environ.setdefault("GIT_AUTHOR_NAME", "AO Bot")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "ao@example.com")
os.environ.setdefault("GIT_COMMITTER_NAME", os.environ.get("GIT_AUTHOR_NAME", "AO Bot"))
os.environ.setdefault("GIT_COMMITTER_EMAIL", os.environ.get("GIT_AUTHOR_EMAIL", "ao@example.com"))

# Secrets / Config
GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
JOBS_MAX_PER_DAY = int(os.environ.get("JOBS_MAX_PER_DAY", "3"))
PORT = int(os.environ.get("PORT", "7860"))
STATE_FILE = "/tmp/ao_jobs_state.json"

def status():
    return {
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
        "JOBS_MAX_PER_DAY": JOBS_MAX_PER_DAY,
        "build": "AO v0.5.2 (Docker Focused)",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\.git)?/?$", (url or "").strip())
    if not m: return None, None
    return m.group(1), m.group(2)

# ---- Context bootstrap into AO repo ----
def _ensure_context_yaml():
    if not (GITHUB_TOKEN and AO_DEFAULT_REPO):
        return {"skipped": "Missing token or AO_DEFAULT_REPO"}
    from git import Repo, Actor
    work = "/tmp/context_boot"
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    try:
        repo = Repo.clone_from(AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@"),
                               os.path.join(work, "repo"))
        ctx_path = os.path.join(work, "repo", "ops", "context.yaml")
        if os.path.exists(ctx_path):
            return {"exists": True}
        # create
        os.makedirs(os.path.dirname(ctx_path), exist_ok=True)
        default_ctx = {
            "intro": "I can create a Hugging Face Space from a GitHub repo. I always dry-run first and only execute after your confirmation.",
            "capabilities": [
                "Clone a public GitHub repo into a new private repo under your GitHub org/user",
                "Create a Hugging Face Space from that repo (Docker SDK)",
            ],
            "guardrails": [
                f"Dry run by default; explicit yes required",
                f"Daily job cap (JOBS_MAX_PER_DAY={JOBS_MAX_PER_DAY})",
                f"HF namespace scoping (HF_NAMESPACE='{HF_NAMESPACE or '(unset)'}')",
            ],
            "examples": [
                "I need to create an HF Space from a repo. What do you need from me?",
                "Repo is https://github.com/gaomingqi/Track-Anything",
                "Call it aow-track-anything on cpu",
            ],
        }
        with open(ctx_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(default_ctx, f, sort_keys=False)
        repo.git.add([ctx_path])
        author = Actor(os.environ.get("GIT_AUTHOR_NAME","AO Bot"), os.environ.get("GIT_AUTHOR_EMAIL","ao@example.com"))
        repo.index.commit("chore(context): add ops/context.yaml (bootstrap)",
                          author=author, committer=author)
        repo.remotes.origin.push()
        return {"created": True}
    except Exception as e:
        return {"error": str(e)}

# ---- Jobs state & rate-limit ----
def _load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"jobs": [], "today": time.strftime("%Y-%m-%d"), "count": 0}

def _save_state(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f)
    except Exception:
        pass

def _rate_limit():
    s = _load_state()
    today = time.strftime("%Y-%m-%d")
    if s.get("today") != today:
        s = {"jobs": [], "today": today, "count": 0}
        _save_state(s)
    if s.get("count", 0) >= JOBS_MAX_PER_DAY:
        return False, f"Daily job limit reached ({JOBS_MAX_PER_DAY})."
    return True, ""

def _record_job(job):
    s = _load_state()
    s["jobs"].append(job)
    s["count"] = s.get("count", 0) + 1
    _save_state(s)

# ---- Conversational flow (single intent) ----
def _extract_fields(text: str):
    url_m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text or "")
    repo_url = url_m.group(0) if url_m else ""
    # name can be "called X" or "name: X"
    name = ""
    m1 = re.search(r"name[:=]\s*([A-Za-z0-9_.\-]+)", text or "")
    if m1: name = m1.group(1)
    m2 = re.search(r"called\s+([A-Za-z0-9_.\-]+)", text or "")
    if m2: name = m2.group(1)
    hw = "cpu-basic"
    if re.search(r"\bgpu\b|\bt4\b", (text or "").lower()): hw = "t4-small"
    if "cpu" in (text or "").lower(): hw = "cpu-basic"
    return {"repo_url": repo_url, "name": name, "hardware": hw}

def jobs_reset():
    # Show banner and ensure context.yaml exists
    ctx_res = _ensure_context_yaml()
    # Load banner (from repo if any; otherwise default)
    banner = "### I can create a Hugging Face Space from a GitHub repo.\n" \
             "I'll ask for anything missing, show a dry‑run plan, and only execute after you confirm.\n\n" \
             "**I’ll need:**\n" \
             "1. GitHub repo URL to clone from\n" \
             "2. A short name for the new worker/Space (e.g., aow-track-anything)\n" \
             "3. (Optional) hardware (cpu-basic default)\n\n" \
             "**Try:**\n" \
             "- Hey AO, I need to create an HF Space from a repo. What do you need from me?\n" \
             "- Repo is https://github.com/gaomingqi/Track-Anything\n" \
             "- Call it aow-track-anything on cpu\n"
    if ctx_res.get("created"): banner += "\n_Context bootstrapped to ops/context.yaml in your AO repo._"
    if ctx_res.get("error"): banner += f"\n_(Context bootstrap error: {ctx_res['error']})_"
    return [("", banner)], ""

def jobs_step(history, user_text):
    history = history or []
    user_text = (user_text or "").strip()
    if not user_text:
        return history + [("","")], ""

    ok, msg = _rate_limit()
    if not ok:
        return history + [(user_text, f"🛑 {msg}")], ""

    fields = _extract_fields(user_text)

    owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
    missing = []
    if not fields["repo_url"]:
        missing.append("the GitHub repo URL to clone from")
    if not fields["name"]:
        missing.append("the desired name for the new worker/Space")
    if not owner:
        missing.append("your GitHub org/user (set AO_DEFAULT_REPO so I can infer it)")

    if missing:
        prompt = "Got it — I can create a Hugging Face Space from a repo. I still need: " + ", ".join(missing) + ".\n" \
                 "You can reply like:\n" \
                 "`repo: https://github.com/owner/repo name: aow-myspace hardware: cpu-basic`"
        return history + [(user_text, prompt)], ""

    plan = {
        "intent": "create_space_from_repo",
        "repo_url": fields["repo_url"],
        "worker_repo": f"{owner}/{fields['name']}",
        "space_id": f"{HF_NAMESPACE or owner}/{fields['name']}",
        "hardware": fields["hardware"],
    }
    history = history + [(user_text, "Here’s the plan (dry‑run):\n```yaml\n" + yaml.safe_dump(plan, sort_keys=False) + "```\nReply **yes** to proceed or edit any field.")]
    if re.search(r"\b(yes|proceed|do it|go ahead)\b", user_text.lower()):
        result = _execute_create_space(owner, plan)
        _record_job({"intent": "create_space_from_repo", "plan": plan, "ts": time.time(), "result": result})
        return history + [("", f"✅ Executed:\n```json\n{json.dumps(result, indent=2)}\n```")], ""
    return history, ""

# ---- Execution helpers ----
def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

def _hf_headers():
    return {"Authorization": f"Bearer {HF_TOKEN}"}

def _execute_create_space(owner, plan):
    import requests
    from git import Repo

    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN missing"}
    if not HF_TOKEN:
        return {"error": "HF_TOKEN missing"}

    # 1) Create GitHub repo (private) if not exists
    repo_name = plan["worker_repo"].split("/")[1]
    check_url = f"https://api.github.com/repos/{owner}/{repo_name}"
    r = requests.get(check_url, headers=_gh_headers(), timeout=30)
    if r.status_code == 200:
        gh = {"exists": True, "repo_url": f"https://github.com/{owner}/{repo_name}"}
    else:
        cr = requests.post("https://api.github.com/user/repos", headers=_gh_headers(),
                           json={"name": repo_name, "private": True, "auto_init": False}, timeout=30)
        if cr.status_code >= 300:
            return {"error": f"GitHub create failed: {cr.status_code} {cr.text[:200]}"}
        gh = {"created": True, "repo_url": f"https://github.com/{owner}/{repo_name}"}

    # 2) Seed repo from source
    work = "/tmp/seed"
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    try:
        src = Repo.clone_from(plan["repo_url"], os.path.join(work, "src"), depth=1)
        dst_auth = gh["repo_url"].replace("https://", f"https://{GITHUB_TOKEN}@")
        dst = Repo.clone_from(dst_auth, os.path.join(work, "dst"))
        # copy contents (excluding .git)
        for root, dirs, files in os.walk(os.path.join(work, "src")):
            if ".git" in root:
                continue
            rel = os.path.relpath(root, os.path.join(work, "src"))
            target_dir = os.path.join(work, "dst", rel)
            os.makedirs(target_dir, exist_ok=True)
            for f in files:
                import shutil as sh
                sh.copy2(os.path.join(root, f), os.path.join(target_dir, f))
        dst.git.add(all=True)
        if dst.is_dirty():
            dst.index.commit("chore(seed): import from source repo")
            dst.remotes.origin.push()
        seed = {"seeded": True}
    except Exception as e:
        return {"error": f"Seeding failed: {e}"}

    # 3) Create HF Space from repo
    ns = HF_NAMESPACE or owner
    space_id = f"{ns}/{repo_name}"
    payload = {"sdk": "docker", "private": True, "hardware": plan["hardware"], "repository": {"url": gh["repo_url"]}}
    sr = requests.post(f"https://huggingface.co/api/spaces/{ns}/{repo_name}", headers=_hf_headers(), json=payload, timeout=60)
    if sr.status_code not in (200, 201):
        return {"github": gh, "seed": seed, "space": {"error": f"HF create space failed: {sr.status_code} {sr.text[:200]}"}};
    sp = {"created": True, "space_id": space_id}

    return {"github": gh, "seed": seed, "space": sp}

# ---- UI ----
with gr.Blocks(title="AO v0.5.2 — Create HF Space from GitHub repo") as demo:
    gr.Markdown("## AO v0.5.2 — Focused conversational flow\nI will help you create a **Hugging Face Space** from a **GitHub repo**.")
    with gr.Tab("Status"):
        env = gr.JSON(label="Environment")
        demo.load(status, outputs=env)
    with gr.Tab("Jobs (conversational)"):
        chat = gr.Chatbot(height=440)
        txt = gr.Textbox(placeholder="Say: Hey AO, I need to create an HF Space from a repo. What do you need from me?")
        send = gr.Button("Send")
        reset = gr.Button("Reset & Bootstrap Context")
        demo.load(fn=jobs_reset, outputs=[chat, txt])
        reset.click(fn=jobs_reset, outputs=[chat, txt])
        send.click(fn=jobs_step, inputs=[chat, txt], outputs=[chat, txt])
        txt.submit(fn=jobs_step, inputs=[chat, txt], outputs=[chat, txt])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

