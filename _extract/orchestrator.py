
import os, io, time, re, tempfile, shutil, pathlib
from typing import Generator, Dict, Any, List, Optional
import requests
from huggingface_hub import HfApi, create_repo, CommitOperationAdd
from git import Repo

from repo_scanner import scan_gpu_need, detect_dockerfiles
from synth_dockerfile import synthesize_dockerfile
from patches import patch_dockerfile_lines

def _detect_version_tag(src_root: str) -> str:
    # Try to read DropXX from README or app title
    try:
        rd = os.path.join(src_root, "README.md")
        if os.path.isfile(rd):
            with open(rd, "r", encoding="utf-8") as f:
                t = f.read()
            m = re.search(r"HF Orchestrator — Drop(\d+)", t)
            if m:
                return f"v{m.group(1)}"
    except Exception:
        pass
    # Fallback to timestamp
    return "v" + time.strftime("%Y%m%d-%H%M%S")

import subprocess, base64

GITHUB_OWNER = "jmdrumsgarrison-ux"
GITHUB_REPO = "HF-Orchestrator"
SecretStrippedByGitPush_ENV = "SecretStrippedByGitPush"

def _github_run(cmd, cwd=None):
    return subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT, text=True)

def _github_sync_release(src_root: str, version_tag: str, logs: List[str]) -> None:  # verbose
    token = os.environ.get(GITHUB_TOKEN_ENV)
    if not token:
        _log(logs, "GitHub sync: GITHUB_TOKEN not set; skipping GitHub publish.")
        return
    try:
        # Local temp git repo
        import tempfile, shutil
        tmp = tempfile.mkdtemp(prefix="ghsync_")
        _log(logs, f"GitHub sync: working dir {tmp}")
        rdst = os.path.join(tmp, "repo")
        os.makedirs(rdst, exist_ok=True)
        # Copy orchestrator files
        import pathlib
        for p in pathlib.Path(src_root).rglob("*"):
            if ".git" in p.parts: 
                continue
            d = os.path.join(rdst, str(p.relative_to(src_root)))
            if p.is_dir():
                os.makedirs(d, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(str(p), d)
        _log(logs, "Git: init repo"); _github_run(["git", "init"], cwd=rdst)
        _github_run(["git", "config", "user.email", "bot@local"], cwd=rdst)
        _github_run(["git", "config", "user.name", "HF Orchestrator Bot"], cwd=rdst)
        _log(logs, "Git: add ."); _github_run(["git", "add", "."], cwd=rdst)
        _log(logs, f"Git: commit {version_tag}"); _github_run(["git", "commit", "-m", f"Orchestrator {version_tag}"], cwd=rdst)
        remote_url = f"https://{token}:x-oauth-basic@github.com/{GITHUB_OWNER}/{GITHUB_REPO}.git"
        _log(logs, "Git: set main"); _github_run(["git", "branch", "-M", "main"], cwd=rdst)
        _log(logs, "Git: add remote origin"); _github_run(["git", "remote", "add", "origin", remote_url], cwd=rdst)
        try:
            _github_run(["git", "push", "-u", "origin", "main"], cwd=rdst)
        except subprocess.CalledProcessError as e:
            _log(logs, f"GitHub push main warning: {e.output}")
        # Tag & push
        _log(logs, f"Git: tag {version_tag}"); _github_run(["git", "tag", version_tag], cwd=rdst)
        try:
            _log(logs, f"Git: push tag {version_tag}"); _github_run(["git", "push", "origin", version_tag], cwd=rdst)
        except subprocess.CalledProcessError as e:
            _log(logs, f"GitHub push tag warning: {e.output}")
        # Create zip artifact
        zip_path = os.path.join(tmp, f"HF_Orchestrator_Space_{version_tag}.zip")
        import zipfile
        _log(logs, "Zip: building artifact");
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for dp, _, fns in os.walk(rdst):
                for fn in fns:
                    full = os.path.join(dp, fn)
                    rel = os.path.relpath(full, rdst)
                    z.write(full, rel)
        # Create release & upload asset
        import requests
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
        repo_api = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        _log(logs, "GitHub: create release");
        rel = requests.post(f"{repo_api}/releases", headers=headers, json={
            "tag_name": version_tag,
            "name": version_tag,
            "body": f"Automated release {version_tag} from HF Orchestrator",
            "draft": False,
            "prerelease": False
        })
        if rel.status_code not in (200,201):
            _log(logs, f"GitHub release create status {rel.status_code}: {rel.text}")
            return
        upload_url = rel.json()["upload_url"].split("{")[0]
        with open(zip_path, "rb") as f:
            data = f.read()
        _log(logs, "GitHub: upload asset");
        up = requests.post(f"{upload_url}?name=HF_Orchestrator_Space_{version_tag}.zip", headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/zip"
        }, data=data)
        _log(logs, f"GitHub release upload: {up.status_code}")
    except Exception as e:
        _log(logs, f"GitHub sync error: {e}")


SecretStrippedByGitPush_ENV = "SecretStrippedByGitPush"

class OrchestratorError(Exception):
    pass

def _log(acc: List[str], line: str) -> Dict[str, Any]:
    acc.append(line)
    return {"log": acc[:]}

def _safe_repo_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")

def _try_download_github_zip(repo_url: str, work: str, logs: List[str]) -> Optional[str]:
    m = re.match(r"https?://github.com/([^/]+)/([^/]+)(?:\.git)?/?", repo_url)
    if not m:
        return None
    user, repo = m.group(1), m.group(2).replace(".git","")
    for branch in ["main", "master"]:
        zip_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"
        _log(logs, f"Trying GitHub zip: {zip_url}")
        r = requests.get(zip_url, timeout=60)
        if r.status_code == 200:
            zpath = os.path.join(work, "repo.zip")
            with open(zpath, "wb") as f:
                f.write(r.content)
            import zipfile
            with zipfile.ZipFile(zpath) as z:
                z.extractall(os.path.join(work, "src"))
            subdirs = [p for p in pathlib.Path(os.path.join(work, "src")).iterdir() if p.is_dir()]
            if subdirs:
                return str(subdirs[0])
    return None

def _shallow_clone(repo_url: str, work: str, logs: List[str]) -> str:
    dst = os.path.join(work, "src")
    _log(logs, f"Falling back to shallow clone: {repo_url}")
    Repo.clone_from(repo_url, dst, depth=1, single_branch=True)
    return dst

def _gather_ops(src_dir: str) -> List[Any]:
    ops: List[Any] = []
    pattern = r'(^|/)(\.git|\.gitattributes|\.gitignore|LICENSE|CODEOWNERS|README(\.md)?|.*\.(pt|bin|safetensors|ckpt|tar|tar\.gz|zip|7z|mp4|mov|avi|mkv|png|jpg|jpeg|gif|webp|onnx))$'
    ignore = re.compile(pattern, re.IGNORECASE)
    for root, _, files in os.walk(src_dir):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), src_dir)
            rel_norm = rel.replace("\\", "/")
            if ignore.search(rel_norm):
                continue
            with open(os.path.join(root, fn), "rb") as f:
                data = f.read()
            ops.append(CommitOperationAdd(path_in_repo=rel_norm, path_or_fileobj=io.BytesIO(data)))
    return ops

def _apply_runtime_prefs(api: HfApi, full_id: str, hardware: Optional[str], logs: List[str]):
    try:
        if hardware:
            _log(logs, f"Requesting hardware: {hardware}")
            api.request_space_hardware(repo_id=full_id, hardware=hardware)
    except Exception as e:
        _log(logs, f"Hardware request skipped (SDK fallback): {e}")

def _wait_for_running(api: HfApi, full_id: str, logs: List[str], timeout_s: int = 1200):
    start = time.time()
    stage_prev = None
    while True:
        try:
            info = api.get_space_runtime(full_id)
            stage = getattr(info, "stage", None) or getattr(info, "runtime_stage", None)
            if stage != stage_prev:
                _log(logs, f"Runtime stage: {stage}")
                stage_prev = stage
            if str(stage).upper() == "RUNNING":
                return
        except Exception as e:
            _log(logs, f"Runtime poll error (continuing): {e}")
        if time.time() - start > timeout_s:
            raise OrchestratorError("Timed out waiting for RUNNING")
        time.sleep(5)

# -------- Auto-repair recipes (Drop66) --------
ERROR_PATTERNS = [
    (r"libgthread-2\.0\.so\.0", "apt_opencv_glib"),
    (r"libGL\.so\.1", "apt_opencv_gl"),
    (r"ffmpeg", "apt_ffmpeg"),
    (r"CUDA_HOME environment variable is not set", "avoid_mmcv_build"),
    (r"invalid device ordinal", "force_cuda0"),
    (r"ModuleNotFoundError: No module named '(\w+)'", "py_path_fix"),
]

def _apply_patch_recipe(df_txt: str, action_key: str) -> str:
    if action_key == "apt_opencv_glib" and "libglib2.0-0" not in df_txt:
        df_txt = df_txt.replace(
            "apt-get install -y --no-install-recommends",
            "apt-get install -y --no-install-recommends libglib2.0-0"
        )
    elif action_key == "apt_opencv_gl" and "libgl1" not in df_txt:
        df_txt = df_txt.replace(
            "apt-get install -y --no-install-recommends",
            "apt-get install -y --no-install-recommends libgl1"
        )
    elif action_key == "apt_ffmpeg" and "ffmpeg" not in df_txt:
        df_txt = df_txt.replace(
            "apt-get install -y --no-install-recommends",
            "apt-get install -y --no-install-recommends ffmpeg"
        )
    elif action_key == "avoid_mmcv_build":
        if "mmcv-lite" not in df_txt:
            df_txt = df_txt.replace("COPY . /workspace/app", "COPY . /workspace/app\nRUN pip install --no-cache-dir mmcv-lite")
        if "sed -i '/mmcv/d'" not in df_txt:
            df_txt = df_txt.replace("RUN pip install --no-cache-dir -r ", "RUN sed -i '/mmcv/d' ")
    elif action_key == "force_cuda0":
        if "CUDA_VISIBLE_DEVICES" not in df_txt:
            df_txt = df_txt.replace("ENV OMP_NUM_THREADS=1", "ENV OMP_NUM_THREADS=1\nENV CUDA_VISIBLE_DEVICES=0")
        if "sed -i \"s/cuda:3/cuda:0/g\"" not in df_txt:
            df_txt = df_txt.replace('python -m pip list &&', 'python -m pip list && sed -i \"s/cuda:3/cuda:0/g\" $(grep -rl \"cuda:3\" /workspace/app) || true &&')
    elif action_key == "py_path_fix":
        if "PYTHONPATH=/workspace/app" not in df_txt:
            df_txt = df_txt.replace("ENV OMP_NUM_THREADS=1", "ENV OMP_NUM_THREADS=1\nENV PYTHONPATH=/workspace/app")

    if "import cv2" in df_txt and "opencv-python-headless" not in df_txt:
        df_txt = df_txt.replace(
            "COPY . /workspace/app",
            "COPY . /workspace/app\nRUN python -c \"import cv2\" || pip install --no-cache-dir opencv-python-headless"
        )
    return df_txt

def _attempt_auto_repair(api: HfApi, full_id: str, dockerfile_bytes: bytes, src_dir: str, logs: List[str], last_error: str) -> bool:
    try:
        df_txt = dockerfile_bytes.decode("utf-8", errors="ignore")
        matched = False
        for rx, action in ERROR_PATTERNS:
            if re.search(rx, last_error):
                matched = True
                df_txt = _apply_patch_recipe(df_txt, action)
        if not matched:
            for action in ["apt_opencv_glib", "apt_opencv_gl", "apt_ffmpeg", "py_path_fix"]:
                df_txt = _apply_patch_recipe(df_txt, action)

        new_df_bytes = df_txt.encode("utf-8")
        ops2 = [
            CommitOperationAdd(path_in_repo="Dockerfile", path_or_fileobj=io.BytesIO(new_df_bytes)),
            CommitOperationAdd(path_in_repo="orchestrator_repair.txt", path_or_fileobj=io.BytesIO(b"Drop66 auto-repair marker"))
        ]
        api.create_commit(repo_id=full_id, repo_type="space", operations=ops2, commit_message="Orchestrator auto-repair (Drop66)")
        _log(logs, "Auto-repair: pushed patched Dockerfile and marker.")
        try:
            api.restart_space(full_id)
        except Exception as e:
            _log(logs, f"Restart request warning (repair): {e}")
        return True
    except Exception as e:
        _log(logs, f"Auto-repair failed to push: {e}")
        return False

def orchestrate(namespace: str, space: str, repo_url: str, hardware: Optional[str], private: bool) -> Generator[Dict[str, Any], None, None]:
    logs: List[str] = []
    if not namespace or not space or not repo_url:
        raise OrchestratorError("Please fill Target Namespace, Target Space, and Git repo URL.")
    token = os.environ.get(HF_TOKEN_ENV)
    if not token:
        _log(logs, "WARNING: HF_TOKEN not set in Space secrets. API calls may fail.")
        yield _log(logs, "Set HF_TOKEN in this Space’s Secrets for write access.")
    api = HfApi(token=token)

    full_id = f"{namespace}/{_safe_repo_name(space)}"
    work = tempfile.mkdtemp(prefix="orchestrator_")
    try:
        yield _log(logs, f"Target Space: {full_id}")
        # Fetch repo
        src_dir = _try_download_github_zip(repo_url, work, logs)
        if not src_dir:
            src_dir = _shallow_clone(repo_url, work, logs)
        yield _log(logs, f"Fetched source at: {src_dir}")

        # Detect hardware
        needs_gpu = scan_gpu_need(src_dir)
        yield _log(logs, f"GPU inference: needs_gpu={needs_gpu}")
        chosen_hw = hardware or ("t4-small" if needs_gpu else None)
        if chosen_hw:
            yield _log(logs, f"Hardware decision: {chosen_hw}")
        else:
            yield _log(logs, "Hardware decision: CPU (no request)")

        # Dockerfile adopt/synthesize
        repo_df = detect_dockerfiles(src_dir)
        if repo_df:
            yield _log(logs, f"Adopted repo Dockerfile: {repo_df}")
            with open(repo_df, "r", encoding="utf-8", errors="ignore") as f:
                df_lines = f.read().splitlines()
        else:
            yield _log(logs, "No Dockerfile found — synthesizing")
            df_lines = synthesize_dockerfile(src_dir).splitlines()

        # Patch Dockerfile
        df_lines = patch_dockerfile_lines(df_lines)
        dockerfile_bytes = ("\n".join(df_lines) + "\n").encode("utf-8")

        # Build ops
        ops = [CommitOperationAdd(path_in_repo="Dockerfile", path_or_fileobj=io.BytesIO(dockerfile_bytes))]
        ops.extend(_gather_ops(src_dir))

        # Create/ensure repo
        try:
            create_repo(repo_id=full_id, repo_type="space", exist_ok=True, private=private, token=token, space_sdk="docker")
            yield _log(logs, "Created/ensured target Space (docker SDK).")
        except Exception as e:
            yield _log(logs, f"Create repo warning: {e}")

        # Hardware request
        _apply_runtime_prefs(api, full_id, chosen_hw, logs)

        # Commit push & restart
        yield _log(logs, f"Pushing {len(ops)} files (batched)…")
        api.create_commit(repo_id=full_id, repo_type="space", operations=ops, commit_message="Orchestrator push (Drop66)")
        yield _log(logs, "Push complete. Restarting Space…")
        try:
            api.restart_space(full_id)
        except Exception as e:
            yield _log(logs, f"Restart request warning: {e}")

        # Wait with up to 3 repairs
        attempts = 0
        while True:
            try:
                _wait_for_running(api, full_id, logs)
                yield {"log": logs, "status": "RUNNING"}
                try:
                    _github_sync_release('/home/user/app', _detect_version_tag('/home/user/app'), logs)
                except Exception as _e:
                    _log(logs, f'GitHub sync skipped: {_e}')

                break
            except Exception as e:
                attempts += 1
                _log(logs, f"Run attempt {attempts} failed: {e}")
                if attempts >= 3:
                    raise
                did = _attempt_auto_repair(api, full_id, dockerfile_bytes, src_dir, logs, str(e))
                if not did:
                    raise
                _log(logs, "Retrying after auto-repair…")

    except Exception as e:
        logs.append(f"BUILD_ERROR: {e}")
        yield {"log": logs, "status": "BUILD_ERROR"}
    finally:
        try:
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass


def manual_github_sync(logs: List[str]) -> Dict[str, Any]:
    try:
        version_tag = _detect_version_tag("/home/user/app")
        _log(logs, f"Manual GitHub sync requested: {version_tag}")
        _github_sync_release("/home/user/app", version_tag, logs)
        return {"log": logs, "status": "SYNCED"}
    except Exception as e:
        logs.append(f"GITHUB_SYNC_ERROR: {e}")
        return {"log": logs, "status": "ERROR"}

