import os, sys, subprocess, json, time, re, shutil
import gradio as gr

OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "")
GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
ALLOWLIST_REPOS = [s.strip() for s in os.environ.get("ALLOWLIST_REPOS","").split(",") if s.strip()]
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
AO_AUTO_COMMIT = os.environ.get("AO_AUTO_COMMIT", "true").lower() != "false"
LAST_CACHE = "/tmp/ao_last_repo.json"
PORT = int(os.environ.get("PORT", "7860"))

def status():
    return {
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "ALLOWLIST_REPOS": ALLOWLIST_REPOS,
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "AO_AUTO_COMMIT": AO_AUTO_COMMIT,
        "python": sys.version.split()[0],
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "build": "AO v0.3.1 (Docker Opinionated)"
    }

# ---------- Helpers ----------
def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)

def _discover_repo_url(user_input: str):
    # 1) explicit
    if user_input and user_input.startswith("http"):
        return user_input.strip(), "input"
    # 2) AO_DEFAULT_REPO
    if AO_DEFAULT_REPO.startswith("http"):
        return AO_DEFAULT_REPO, "env:AO_DEFAULT_REPO"
    # 3) allowlist singleton
    if len(ALLOWLIST_REPOS) == 1:
        return f"https://github.com/{ALLOWLIST_REPOS[0]}", "env:ALLOWLIST_REPOS"
    # 4) last used cache
    try:
        with open(LAST_CACHE, "r") as f:
            cached = json.load(f).get("repo_url", "")
            if cached.startswith("http"):
                return cached, "cache"
    except Exception:
        pass
    return "", "missing"

def _cache_repo_url(url: str):
    try:
        with open(LAST_CACHE, "w") as f:
            json.dump({"repo_url": url, "ts": time.time()}, f)
    except Exception:
        pass

def _auto_plan(repo_url: str):
    owner, repo = _owner_repo_from_url(repo_url)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"""# Agentic Orchestrator Plan

**Version**: AO v0.3.1 (Docker Opinionated)
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
- ALLOWLIST_REPOS; AO_DEFAULT_REPO; AO_AUTO_COMMIT heuristic.
- Writes limited to ops/.
"""

def _auto_log_entry():
    return f"Initialized/updated by AO @ {time.strftime('%Y-%m-%d %H:%M:%S')}"

def _safe_to_commit(diff_text: str, staged_paths):
    if not AO_AUTO_COMMIT:
        return False, "AO_AUTO_COMMIT=false"
    if any((p.startswith("../") or ".." in p) for p in staged_paths):
        return False, "suspicious paths"
    if not all(p.startswith("ops/") for p in staged_paths):
        return False, "changes outside ops/"
    if len(diff_text.encode("utf-8")) > 100_000:
        return False, "diff too large"
    return True, "ok"

# ---------- Save Progress (opinionated) ----------
RW_WORKDIR = "/tmp/repo_rw"

def save_progress_auto(repo_url_input):
    repo_url, source = _discover_repo_url(repo_url_input or "")
    if not repo_url:
        return json.dumps({"error": "No repo URL available. Provide one or set AO_DEFAULT_REPO / ALLOWLIST_REPOS."}, indent=2)

    owner, repo = _owner_repo_from_url(repo_url)
    if not owner:
        return json.dumps({"error": "Repo URL must be https://github.com/owner/repo"}, indent=2)

    # allowlist check (if set)
    if ALLOWLIST_REPOS and f"{owner}/{repo}" not in ALLOWLIST_REPOS:
        return json.dumps({"error": f"{owner}/{repo} not in ALLOWLIST_REPOS {ALLOWLIST_REPOS}"}, indent=2)

    if not GITHUB_TOKEN:
        return json.dumps({"error": "GITHUB_TOKEN not set; cannot push."}, indent=2)

    from git import Repo, Actor, GitCommandError

    os.makedirs(RW_WORKDIR, exist_ok=True)
    local = os.path.join(RW_WORKDIR, "repo")
    if os.path.exists(local):
        shutil.rmtree(local, ignore_errors=True)

    src_auth = repo_url.replace("https://", f"https://{GITHUB_TOKEN}@")
    try:
        repo_obj = Repo.clone_from(src_auth, local, depth=1)
    except Exception as e:
        return json.dumps({"error": f"Clone failed: {e}"}, indent=2)

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

    plan_text = _auto_plan(repo_url)
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
                return json.dumps({"repo": repo_url, "source": source, "bootstrap": True, "dry_run": True, "reason": why, "diff_preview": diff_text}, indent=2)
            author = Actor("AO Bot", "ao@example.com")
            repo_obj.index.commit("chore(ops): bootstrap AO files")
            repo_obj.git.push("--set-upstream", "origin", "main")
            _cache_repo_url(repo_url)
            return json.dumps({
                "repo": repo_url, "branch": "main (new)", "bootstrap": True, "committed": staged,
                "links": {
                    "plan": f"{repo_url}/blob/main/ops/plan.md",
                    "logbook": f"{repo_url}/blob/main/ops/logbook.md"
                }
            }, indent=2)

        # existing repo
        # resolve default branch via origin/HEAD
        target_branch = None
        try:
            sym = repo_obj.git.symbolic_ref("refs/remotes/origin/HEAD")
            # e.g., refs/remotes/origin/main
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
            return json.dumps({"repo": repo_url, "branch": target_branch or "(auto)", "dry_run": True, "reason": why, "diff_preview": diff_text}, indent=2)
        author = Actor("AO Bot", "ao@example.com")
        repo_obj.index.commit("chore(ops): update plan/logbook via AO")
        repo_obj.remotes.origin.push()
        _cache_repo_url(repo_url)
        return json.dumps({
            "repo": repo_url, "branch": target_branch or "(auto)", "committed": staged,
            "links": {
                "plan": f"{repo_url}/blob/{target_branch or 'main'}/ops/plan.md",
                "logbook": f"{repo_url}/blob/{target_branch or 'main'}/ops/logbook.md"
            }
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Save failed: {e}"}, indent=2)

# ---------- UI ----------
with gr.Blocks(title="Agentic Orchestrator (AO) v0.3.1 — Docker") as demo:
    gr.Markdown("## AO v0.3.1 — Docker (Opinionated defaults)\nClick **Run** — AO will infer the repo, branch, plan, and commit safely.")

    with gr.Tab("Status"):
        btn_stat = gr.Button("Check Status")
        out_stat = gr.JSON(label="Environment")
        btn_stat.click(fn=status, outputs=out_stat)
        demo.load(status, outputs=out_stat)

    with gr.Tab("Save Progress (Auto)"):
        repo_in = gr.Textbox(label="Repository URL (optional)", placeholder="Leave blank to auto-discover")
        run_btn = gr.Button("Run")
        out = gr.Code(label="Result (JSON)")
        run_btn.click(fn=save_progress_auto, inputs=repo_in, outputs=out)

    with gr.Tab("Git (read-only)"):
        url = gr.Textbox(label="Repository URL", placeholder="https://github.com/owner/repo")
        btn_git = gr.Button("Clone / Refresh (depth=1)")
        out_git = gr.Code(label="Repo Info (JSON)")
        # Reuse the read-only function from prior versions
        def git_read(repo_url):
            from git import Repo
            work = "/tmp/repo_ro"
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
        btn_git.click(fn=git_read, inputs=url, outputs=out_git)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

