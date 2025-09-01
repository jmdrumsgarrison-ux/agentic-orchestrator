from typing import List

def patch_dockerfile_lines(lines: List[str]) -> List[str]:
    out = list(lines)

    injected = []

    if not any(' bash ' in l or l.strip().startswith('RUN apt-get') and 'bash' in l for l in out):
        injected.append('RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*')
    if not any("PYTHONPATH=" in l for l in out):
        injected.append('ENV PYTHONPATH=/workspace/app')
    if not any("CUDA_VISIBLE_DEVICES" in l for l in out):
        injected.append('ENV CUDA_VISIBLE_DEVICES=0')
    if not any("DEBIAN_FRONTEND=noninteractive" in l for l in out):
        injected.append('ENV DEBIAN_FRONTEND=noninteractive')
    if not any(("tzdata" in l and "apt-get" in l) or ("libglib2.0-0" in l) for l in out):
        injected.append('RUN apt-get update && apt-get install -y --no-install-recommends tzdata libglib2.0-0 libgl1 libsm6 libxext6 libxrender1 ffmpeg && rm -rf /var/lib/apt/lists/*')
    if not any("OMP_NUM_THREADS" in l for l in out):
        injected.append('ENV OMP_NUM_THREADS=1')
    if not any("/workspace/app/user" in l for l in out):
        injected.append('RUN mkdir -p /workspace/app/user && chmod -R a+rwx /workspace || true')

    # Place injections after first FROM
    result = []
    placed = False
    for ln in out:
        result.append(ln)
        if not placed and ln.strip().lower().startswith("from "):
            for add in injected:
                result.append(add)
            placed = True
    if not placed:
        result = injected + result
    return result
