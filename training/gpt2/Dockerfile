# AMD64 manifest of rayproject/ray:2.55.1-py312-cu128, verified before build.
FROM rayproject/ray@sha256:70a385b25198480cc37f8ed5382160e2b1c89dd71115bc4db337dcc8966d9183
COPY requirements.txt /tmp/gpt2-requirements.txt
# Ray's optional CuPy is unused and constrains NumPy below the pilot's version.
RUN pip uninstall -y cupy-cuda12x
RUN --mount=type=cache,target=/home/ray/.cache/pip,uid=1000,gid=1000 pip install -r /tmp/gpt2-requirements.txt
RUN pip check
# Prepare the pinned, checksum-verified checkpoint locally; never download floating weights.
COPY --chown=ray:users work/weights /opt/gpt2
ENV HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2
# Trainer code is supplied by the existing content-addressed Ray archive.
# No CUDA initialization on import: the same image must start on a CPU head.
RUN python -c "import ray, torch, transformers; assert ray.__version__ == '2.55.1'; print(torch.__version__, torch.version.cuda)"
