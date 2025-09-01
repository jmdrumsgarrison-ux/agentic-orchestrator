import os, pathlib

GPU_HINTS = [
    "torch.cuda", "cuda", "xformers", "flash-attn", "triton", "accelerate",
    "pytorch-cuda", "tensorflow-gpu", "bitsandbytes", "device_map", "bfloat16"
]

def _read_text(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def scan_gpu_need(src_dir: str) -> bool:
    # Requirements
    for root, _, files in os.walk(src_dir):
        for fn in files:
            low = fn.lower()
            if low.startswith("requirements") and low.endswith(".txt"):
                txt = _read_text(os.path.join(root, fn)).lower()
                if any(k in txt for k in ["torch", "xformers", "pytorch-cuda", "flash-attn", "triton", "tensorflow-gpu", "bitsandbytes"]):
                    return True

    # Dockerfile
    for dp in detect_dockerfiles(src_dir, return_all=True):
        txt = _read_text(dp).lower()
        if any(k in txt for k in ["pytorch", "cuda", "nvidia", "xformers", "bitsandbytes", "tensorflow-gpu", "pytorch-cuda"]):
            return True

    # README / code
    for root, _, files in os.walk(src_dir):
        for fn in files:
            if fn.lower().endswith((".md", ".py")):
                txt = _read_text(os.path.join(root, fn)).lower()
                if any(k in txt for k in ["cuda", "gpu", "nvidia", "torch.cuda", "flash-attn"]):
                    return True
    return False

def detect_dockerfiles(src_dir: str, return_all: bool=False):
    cands = []
    for rel in ["Dockerfile", "docker/Dockerfile", "dockerfile", "Dockerfile.dev", "Dockerfile.prod"]:
        p = os.path.join(src_dir, rel)
        if os.path.isfile(p):
            cands.append(p)
    if return_all:
        return cands
    return cands[0] if cands else None
