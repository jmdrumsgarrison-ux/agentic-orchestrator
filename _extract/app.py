import os, sys, json, time, re, shutil, yaml, gradio as gr
from markdown_it import MarkdownIt

HOME_DIR = "/tmp/ao_home"
os.makedirs(HOME_DIR, exist_ok=True)
os.environ.setdefault("HOME", HOME_DIR)
os.environ.setdefault("GIT_AUTHOR_NAME", "AO Bot")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "ao@example.com")
os.environ.setdefault("GIT_COMMITTER_NAME", os.environ.get("GIT_AUTHOR_NAME", "AO Bot"))
os.environ.setdefault("GIT_COMMITTER_EMAIL", os.environ.get("GIT_AUTHOR_EMAIL", "ao@example.com"))

GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
JOBS_MAX_PER_DAY = int(os.environ.get("JOBS_MAX_PER_DAY", "3"))
PORT = int(os.environ.get("PORT", "7860"))

def status():
    return {
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
        "JOBS_MAX_PER_DAY": JOBS_MAX_PER_DAY,
        "build": "AO v0.5.4r2 (Docker Self‑Knowledge + Repo Search)",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\.git)?/?$", (url or "").strip())
    if not m: return None, None
    return m.group(1), m.group(2)

# ---------- Repo helpers ----------
def _clone_ao_repo(workdir):
    from git import Repo
    if not (GITHUB_TOKEN and AO_DEFAULT_REPO):
        raise RuntimeError("Missing GITHUB_TOKEN or AO_DEFAULT_REPO")
    if os.path.exists(workdir): shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)
    repo = Repo.clone_from(AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@"),
                           os.path.join(workdir, "repo"), depth=1)
    return repo, os.path.join(workdir, "repo")

def _read_lines(base, rel):
    p = os.path.join(base, rel)
    if not os.path.exists(p): return []
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        return f.read().splitlines()

def _md_plain(md_text: str, max_chars=1200):
    text = md_text
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars] + ("…" if len(text) > max_chars else "")

# ---------- Friendly context ----------
FRIENDLY_BANNER = (
    "👋 Hi, I’m AO — that stands for Agentic Orchestrator.\n\n"
    "I’ll eventually have lots of abilities, but right now I’m focused on one big job: "
    "**turning public GitHub repositories into working Hugging Face Spaces.**\n\n"
    "If something goes wrong along the way (like install errors), I keep patching and retrying until it runs — "
    "so you don’t have to wrestle with the setup.\n\n"
    "I’m powered by ChatGPT, so you can also just chat with me about ideas, repos, or tools you might want to explore. "
    "But my *specialty today* is:\n\n"
    "**“Give me a GitHub repo, and I’ll get it running as a Hugging Face Space for you.”**\n\n"
    "👉 Just tell me what you’d like to do, in your own words. I’ll ask questions if I need more details.\n"
    "\n**Try:**\n- what can you do right now?\n- show last job\n- create a space from https://github.com/owner/repo called aow-myspace on cpu\n"
)

# ---------- Lightweight search ----------
STOPWORDS = set("""a an and are as at be by for from has have how i in is it its of on or that the to what when where which who why will with you your""".split())

def _normalize(t): 
    return re.findall(r"[a-z0-9]+", (t or "").lower())

def _score_line(tokens_q, tokens_l):
    s = sum(1 for t in tokens_l if t in tokens_q and t not in STOPWORDS)
    q_str = " ".join(tokens_q)
    l_str = " ".join(tokens_l)
    if len(tokens_q) >= 2 and " ".join(tokens_q[:2]) in l_str:
        s += 2
    return s

def repo_search(query: str):
    try:
        _, base = _clone_ao_repo("/tmp/ao_search")
    except Exception as e:
        return f"I couldn't read the AO repo yet ({e})."
    files = ["ops/plan.md", "ops/logbook.md", "ops/context.yaml"]
    q_tokens = _normalize(query)
    hits = []
    for rel in files:
        lines = _read_lines(base, rel)
        for idx, line in enumerate(lines):
            tok = _normalize(line)
            score = _score_line(q_tokens, tok)
            if score <= 0: 
                continue
            start = max(0, idx-2); end = min(len(lines), idx+3)
            snippet = "\n".join(lines[start:end])
            hits.append((score, rel, idx+1, snippet))
    hits.sort(key=lambda x: (-x[0], x[1], x[2]))
    if not hits:
        return "I didn’t find anything in my docs for that. Try rephrasing or ask directly (“what can you do right now?”, “show last job”)."
    out = []
    for score, rel, line_no, snip in hits[:3]:
        quoted = snip.replace("\n", "\n> ")
        out.append(f"**{rel}** — line {line_no}\n> {quoted}\n")
    return "\n".join(out)

# ---------- Intents ----------
def _intent(text: str):
    t = (text or "").lower()
    if any(k in t for k in ["what can you do", "capabilities", "help", "what do you do"]):
        return "ask_context"
    if any(k in t for k in ["architecture", "plan", "how are you built", "how are you coded"]):
        return "ask_plan"
    if any(k in t for k in ["logbook", "last job", "history", "what happened today", "recent job"]):
        return "ask_logbook"
    if any(k in t for k in ["create a space", "create an hf space", "clone into a space", "make a space", "space from repo"]):
        return "create_space"
    return "ask_docs"

def _extract_fields(text: str):
    url_m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text or "")
    repo_url = url_m.group(0) if url_m else ""
    name = ""
    m1 = re.search(r"name[:=]\s*([A-Za-z0-9_.\-]+)", text or "")
    if m1: name = m1.group(1)
    m2 = re.search(r"called\s+([A-Za-z0-9_.\-]+)", text or "")
    if m2: name = m2.group(1)
    hw = "cpu-basic"
    if re.search(r"\bgpu\b|\bt4\b", (text or "").lower()): hw = "t4-small"
    if "cpu" in (text or "").lower(): hw = "cpu-basic"
    return {"repo_url": repo_url, "name": name, "hardware": hw}

# ---------- Execution helpers (unchanged) ----------
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

    work = "/tmp/seed"
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    try:
        src = Repo.clone_from(plan["repo_url"], os.path.join(work, "src"), depth=1)
        dst_auth = gh["repo_url"].replace("https://", f"https://{GITHUB_TOKEN}@")
        dst = Repo.clone_from(dst_auth, os.path.join(work, "dst"))
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

    ns = HF_NAMESPACE or owner
    space_id = f"{ns}/{repo_name}"
    payload = {"sdk": "docker", "private": True, "hardware": plan["hardware"], "repository": {"url": gh["repo_url"]}}
    import requests
    sr = requests.post(f"https://huggingface.co/api/spaces/{ns}/{repo_name}", headers=_hf_headers(), json=payload, timeout=60)
    if sr.status_code not in (200, 201):
        return {"github": gh, "seed": seed, "space": {"error": f"HF create space failed: {sr.status_code} {sr.text[:200]}"}};
    sp = {"created": True, "space_id": space_id}

    return {"github": gh, "seed": seed, "space": sp}

# ---------- Chat ----------
def jobs_reset():
    return [("", FRIENDLY_BANNER)], ""

def jobs_step(history, user_text):
    history = history or []
    user_text = (user_text or "").strip()
    if not user_text:
        return history + [("","")], ""

    intent = _intent(user_text)

    if intent == "ask_context":
        try:
            _, base = _clone_ao_repo("/tmp/ao_read_ctx")
            ctx = _read_lines(base, "ops/context.yaml")
            if not ctx:
                return history + [(user_text, FRIENDLY_BANNER)], ""
            preview = "\n".join(ctx[:60])
            return history + [(user_text, f"Here’s my current context banner (from `ops/context.yaml`):\n\n> " + preview.replace("\n","\n> "))], "" 
        except Exception as e:
            return history + [(user_text, f"I couldn’t load the context yet ({e}).")], ""

    if intent == "ask_plan":
        try:
            _, base = _clone_ao_repo("/tmp/ao_read_plan")
            plan = _read_lines(base, "ops/plan.md")
            if not plan:
                return history + [(user_text, "I couldn’t find `ops/plan.md` yet.")], ""
            preview = "\n".join(plan[:80])
            return history + [(user_text, f"Plan preview (`ops/plan.md`):\n\n> " + preview.replace("\n","\n> "))], ""
        except Exception as e:
            return history + [(user_text, f"I couldn’t load the plan yet ({e}).")], ""

    if intent == "ask_logbook":
        try:
            _, base = _clone_ao_repo("/tmp/ao_read_log")
            lines = _read_lines(base, "ops/logbook.md")
            if not lines:
                return history + [(user_text, "The logbook is empty so far.")], ""
            text = "\n".join(lines)
            sections = re.split(r"\n##\s+", text)
            last = sections[-1] if len(sections) > 1 else text
            title, body = (last.split("\n",1)+[""])[:2]
            body_preview = _md_plain(body, 1000)
            return history + [(user_text, f"**Most recent entry** — {title.strip()}\n\n{body_preview}")], ""
        except Exception as e:
            return history + [(user_text, f"I couldn’t load the logbook yet ({e}).")], ""

    if intent == "create_space":
        fields = _extract_fields(user_text)
        owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
        missing = []
        if not fields["repo_url"]: missing.append("the GitHub repo URL to clone from")
        if not fields["name"]: missing.append("the desired name for the new worker/Space")
        if not owner: missing.append("your GitHub org/user (set AO_DEFAULT_REPO so I can infer it)")
        if missing:
            prompt = "Got it — I can create a Space from a repo, but I still need: " + ", ".join(missing) + ".\n" \
                     "For example:\n`repo: https://github.com/owner/repo name: aow-myspace hardware: cpu-basic`"
            return history + [(user_text, prompt)], ""
        plan = {
            "intent": "create_space_from_repo",
            "repo_url": fields["repo_url"],
            "worker_repo": f"{owner}/{fields['name']}",
            "space_id": f"{HF_NAMESPACE or owner}/{fields['name']}",
            "hardware": fields["hardware"],
        }
        history = history + [(user_text, "Here’s the plan (dry‑run):\n```yaml\n" + yaml.safe_dump(plan, sort_keys=False) + "```\nReply **yes** to proceed.")]
        if re.search(r"\b(yes|proceed|do it|go ahead)\b", user_text.lower()):
            result = _execute_create_space(owner, plan)
            try:
                from git import Repo, Actor as A
                work = "/tmp/log_write"
                if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
                os.makedirs(work, exist_ok=True)
                repo = Repo.clone_from(AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@"),
                                    os.path.join(work, "repo"))
                ops_dir = os.path.join(work, "repo", "ops")
                os.makedirs(ops_dir, exist_ok=True)
                logp = os.path.join(ops_dir, "logbook.md")
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                entry = f"\n## {ts} — Create HF Space from GitHub repo\n\n**Plan**\n```yaml\n{yaml.safe_dump(plan, sort_keys=False)}\n```\n**Result**\n```json\n{json.dumps(result, indent=2)}\n```\n"
                mode = "a" if os.path.exists(logp) else "w"
                with open(logp, mode, encoding="utf-8") as f:
                    if mode == "w":
                        f.write("# AO Logbook\n")
                    f.write(entry)
                repo.git.add([logp])
                author = A(os.environ.get("GIT_AUTHOR_NAME","AO Bot"), os.environ.get("GIT_AUTHOR_EMAIL","ao@example.com"))
                repo.index.commit(f"chore(log): record job — Create HF Space from GitHub repo", author=author, committer=author)
                repo.remotes.origin.push()
            except Exception:
                pass
            return history + [("", f"✅ Executed:\n```json\n{json.dumps(result, indent=2)}\n```")], ""
        return history, ""

    ans = repo_search(user_text)
    return history + [(user_text, ans)], ""

with gr.Blocks(title="AO v0.5.4r2 — Self‑Knowledge + Repo Search + Action") as demo:
    gr.Markdown("## AO v0.5.4r2 — Ask me about myself, search my docs, or ask me to create a Space from a repo.")
    with gr.Tab("Status"):
        env = gr.JSON(label="Environment")
        demo.load(status, outputs=env)
    with gr.Tab("Jobs (conversational)"):
        chat = gr.Chatbot(height=480)
        txt = gr.Textbox(placeholder="Try: what can you do right now? — show last job — or — create a space from https://github.com/...")
        send = gr.Button("Send")
        reset = gr.Button("Reset")
        demo.load(fn=jobs_reset, outputs=[chat, txt])
        reset.click(fn=jobs_reset, outputs=[chat, txt])
        send.click(fn=jobs_step, inputs=[chat, txt], outputs=[chat, txt])
        txt.submit(fn=jobs_step, inputs=[chat, txt], outputs=[chat, txt])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

