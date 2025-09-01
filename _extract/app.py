import os, sys, json, time, re, shutil
import gradio as gr

# --- Hardening for slim containers ---
HOME_DIR = "/tmp/ao_home"
try:
    os.makedirs(HOME_DIR, exist_ok=True)
except Exception:
    HOME_DIR = "/tmp"
os.environ.setdefault("HOME", HOME_DIR)
os.environ.setdefault("GIT_AUTHOR_NAME", "AO Bot")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "ao@example.com")
os.environ.setdefault("GIT_COMMITTER_NAME", os.environ.get("GIT_AUTHOR_NAME", "AO Bot"))
os.environ.setdefault("GIT_COMMITTER_EMAIL", os.environ.get("GIT_AUTHOR_EMAIL", "ao@example.com"))

OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "")
GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
AO_AUTO_COMMIT = os.environ.get("AO_AUTO_COMMIT", "true").lower() != "false"
PORT = int(os.environ.get("PORT", "7860"))

def status():
    return {
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "AO_AUTO_COMMIT": AO_AUTO_COMMIT,
        "HOME": os.environ.get("HOME"),
        "build": "AO v0.3.3 (Docker Opinionated)",
        "python": sys.version.split()[0],
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

def _owner_repo_from_url(url: str):
    import re
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)

def _auto_plan(repo_url: str):
    owner, repo = _owner_repo_from_url(repo_url)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"""# Agentic Orchestrator Plan

**Version**: AO v0.3.3 (Docker Opinionated)
**Repo**: {owner}/{repo}
**When**: {now}

## Goals
- Establish durable lineage (`ops/plan.md`, `ops/logbook.md`).
- Enable safe, incremental automation (AO/AOW).
- Guardrails for tokens, rate limits, and spawn control.

## Phases
1. Bootstrap repo with ops bundle.
2. Read-only Git + Ask (quota permitting).
3. Controlled write ops (ops/* only).
4. Later: worker spawning & Space orchestration.

## Acceptance
- ops files exist and are kept current.
- commits are scoped; no runaway changes.
- clear rollback via Git tags.

## Guardrails
- AO_DEFAULT_REPO; AO_AUTO_COMMIT heuristic.
- Writes limited to ops/.
"""

def _auto_log_entry():
    return f"Initialized/updated by AO @ {time.strftime('%Y-%m-%d %H:%M:%S')}"

def _safe_to_commit(diff_text: str, staged_paths):
    if not AO_AUTO_COMMIT:
        return False, "AO_AUTO_COMMIT=false"
    if any((p.startswith('../') or '..' in p) for p in staged_paths):
        return False, "suspicious paths"
    if not all(p.startswith('ops/') for p in staged_paths):
        return False, "changes outside ops/"
    if len(diff_text.encode('utf-8')) > 100_000:
        return False, "diff too large"
    return True, "ok"

RW_WORKDIR = "/tmp/repo_rw"
RO_WORKDIR = "/tmp/repo_ro"

def save_progress_auto():
    if not AO_DEFAULT_REPO:
        return json.dumps({"error": "AO_DEFAULT_REPO is not set. Go to Settings → Variables and secrets."}, indent=2)
    if not GITHUB_TOKEN:
        return json.dumps({"error": "GITHUB_TOKEN not set; cannot push."}, indent=2)

    from git import Repo, Actor

    os.makedirs(RW_WORKDIR, exist_ok=True)
    local = os.path.join(RW_WORKDIR, "repo")
    if os.path.exists(local):
        shutil.rmtree(local, ignore_errors=True)

    src_auth = AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@")
    try:
        repo_obj = Repo.clone_from(src_auth, local, depth=1)
    except Exception as e:
        return json.dumps({"error": f"Clone failed: {e}"}, indent=2)

    # repo-local identity
    try:
        with repo_obj.config_writer() as cw:
            cw.set_value("user", "name", os.environ.get("GIT_AUTHOR_NAME", "AO Bot"))
            cw.set_value("user", "email", os.environ.get("GIT_AUTHOR_EMAIL", "ao@example.com"))
    except Exception:
        pass

    def repo_is_empty(r):
        try:
            if r.head.is_valid():
                return False
        except Exception:
            pass
        try:
            return len(list(r.refs)) == 0
        except Exception:
            return True

    plan_text = _auto_plan(AO_DEFAULT_REPO)
    log_text = _auto_log_entry()

    try:
        if repo_is_empty(repo_obj):
            repo_obj.git.checkout("--orphan", "main")
            ops_dir = os.path.join(local, "ops")
            os.makedirs(ops_dir, exist_ok=True)
            with open(os.path.join(ops_dir, "plan.md"), "w", encoding="utf-8") as f:
                f.write(plan_text)
            with open(os.path.join(ops_dir, "logbook.md"), "a", encoding="utf-8") as f:
                f.write(f"## {time.strftime('%Y-%m-%d %H:%M:%S')}\nInitialized AO logbook.\n")
            repo_obj.git.add(all=True)
            diff_text = repo_obj.git.diff("--cached")
            staged = ["ops/plan.md", "ops/logbook.md"]
            ok, why = _safe_to_commit(diff_text, staged)
            if not ok:
                repo_obj.git.reset()
                return json.dumps({"repo": AO_DEFAULT_REPO, "bootstrap": True, "dry_run": True, "reason": why, "diff_preview": diff_text}, indent=2)
            author = Actor(os.environ.get("GIT_AUTHOR_NAME","AO Bot"), os.environ.get("GIT_AUTHOR_EMAIL","ao@example.com"))
            repo_obj.index.commit("chore(ops): bootstrap AO files", author=author, committer=author)
            repo_obj.git.push("--set-upstream", "origin", "main")
            return json.dumps({
                "repo": AO_DEFAULT_REPO, "branch": "main (new)", "bootstrap": True, "committed": staged,
                "links": {
                    "plan": f"{AO_DEFAULT_REPO}/blob/main/ops/plan.md",
                    "logbook": f"{AO_DEFAULT_REPO}/blob/main/ops/logbook.md"
                }
            }, indent=2)

        # existing repo
        target_branch = None
        try:
            sym = repo_obj.git.symbolic_ref("refs/remotes/origin/HEAD")
            target_branch = sym.rsplit("/", 1)[-1]
        except Exception:
            for b in ["main", "master"]:
                if b in repo_obj.refs:
                    target_branch = b
                    break
        if target_branch:
            repo_obj.git.checkout(target_branch)

        ops_dir = os.path.join(local, "ops")
        os.makedirs(ops_dir, exist_ok=True)
        with open(os.path.join(ops_dir, "plan.md"), "w", encoding="utf-8") as f:
            f.write(plan_text)
        with open(os.path.join(ops_dir, "logbook.md"), "a", encoding="utf-8") as f:
            f.write(f"\n## {time.strftime('%Y-%m-%d %H:%M:%S')}\n{log_text}\n")
        repo_obj.git.add([os.path.join(ops_dir, "plan.md"), os.path.join(ops_dir, "logbook.md")])
        diff_text = repo_obj.git.diff("--cached")
        staged = ["ops/plan.md", "ops/logbook.md"]
        ok, why = _safe_to_commit(diff_text, staged)
        if not ok:
            repo_obj.git.reset()
            return json.dumps({"repo": AO_DEFAULT_REPO, "branch": target_branch or "(auto)", "dry_run": True, "reason": why, "diff_preview": diff_text}, indent=2)
        author = Actor(os.environ.get("GIT_AUTHOR_NAME","AO Bot"), os.environ.get("GIT_AUTHOR_EMAIL","ao@example.com"))
        repo_obj.index.commit("chore(ops): update plan/logbook via AO", author=author, committer=author)
        repo_obj.remotes.origin.push()
        return json.dumps({
            "repo": AO_DEFAULT_REPO, "branch": target_branch or "(auto)", "committed": staged,
            "links": {
                "plan": f"{AO_DEFAULT_REPO}/blob/{target_branch or 'main'}/ops/plan.md",
                "logbook": f"{AO_DEFAULT_REPO}/blob/{target_branch or 'main'}/ops/logbook.md"
            }
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Save failed: {e}"}, indent=2)

# --- Read-only Git tab retained for visibility ---
def git_read(repo_url):
    from git import Repo
    work = RO_WORKDIR
    os.makedirs(work, exist_ok=True)
    local = os.path.join(work, "repo")
    info = {"repo_url": repo_url, "workdir": work, "action": "", "error": None}
    try:
        if os.path.exists(os.path.join(local, ".git")):
            repo = Repo(local)
            info["action"] = "fetch"
            repo.git.fetch("--depth=1", "origin")
            repo.git.checkout("FETCH_HEAD")
        else:
            src = repo_url.strip()
            if GITHUB_TOKEN and src.startswith("https://github.com/"):
                src = src.replace("https://", f"https://{GITHUB_TOKEN}@")
            info["action"] = "clone"
            repo = Repo.clone_from(src, local, depth=1)
        head = repo.head.commit
        info["head"] = {"sha": head.hexsha, "message": head.message.strip(), "author": str(head.author), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(head.committed_date))}
        try:
            info["branches"] = [h.name for h in repo.remotes.origin.refs][:10]
        except Exception:
            info["branches"] = []
        commits = []
        for c in repo.iter_commits(max_count=5):
            commits.append({"sha": c.hexsha, "msg": c.message.strip().splitlines()[0], "author": str(c.author), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(c.committed_date))})
        info["recent_commits"] = commits
        return json.dumps(info, indent=2)
    except Exception as e:
        info["error"] = str(e)
        return json.dumps(info, indent=2)

with gr.Blocks(title="Agentic Orchestrator (AO) v0.3.3 — Docker") as demo:
    gr.Markdown("## AO v0.3.3 — Docker (Opinionated, single-source repo)\nSet AO_DEFAULT_REPO once; click **Run**.")

    with gr.Tab("Status"):
        out_stat = gr.JSON(label="Environment")
        demo.load(status, outputs=out_stat)

    with gr.Tab("Save Progress (Auto)"):
        run_btn = gr.Button("Run")
        out = gr.Code(label="Result (JSON)")
        run_btn.click(fn=save_progress_auto, outputs=out)

    with gr.Tab("Git (read-only)"):
        url = gr.Textbox(label="Repository URL", placeholder="https://github.com/owner/repo")
        btn_git = gr.Button("Clone / Refresh (depth=1)")
        out_git = gr.Code(label="Repo Info (JSON)")
        btn_git.click(fn=git_read, inputs=url, outputs=out_git)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

