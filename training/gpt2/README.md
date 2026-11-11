# GPT-2 smoke on local Crucible

One GPT-2 small full-weight pilot: 20,000 eligible source rows for one epoch,
20,000 **saved** fold-0 training IDs for one epoch, 10,000 saved held-out IDs,
one target-first scoring order, FP32 and the training-label prior. This is an
infrastructure/parity experiment, not evidence of predictive improvement.
Public-demo configs are untouched. All commands below use this directory's
isolated `configs/` root and local Hub; never run them from the public-demo root.

Prepared from Platform PR #1461 head `edb43986788296e8e86ec9311dc64c8f6b737570`.
The exact dataset, split, trainer and image identities live in `manifests/`.
GPT-2 revision: `openai-community/gpt2@607a30d783dfa663caf39e06633721c8d4cfcd7e`.
Ray is 2.55.1. The trainer runs as one `ray.remote(num_gpus=1)` task; the head
advertises zero task CPUs/GPUs. No Chronon runtime or modelpg files were changed.

Preparation evidence: 12 native CPU tests and 12 tests inside the AMD64 image
passed; the image passed `pip check` and started a zero-GPU Ray head. Packaged
weight checksums and a full GPT-2 CPU forward pass also passed. ECR confirmed
the exact digest recorded in `manifests/artifacts.json`. The exact
compiled model `default.gpt2.smoke__914323868f4f` passed local training-source
validation. This does not validate GPU execution or inference. See
`manifests/verification.json`; no new GPU metrics exist.

The existing local trial is `56538208-dd78-4922-b760-3ed7264fb424`, experiment
`pilot-parity-f0-s42` (**PLANNED**). Resume these IDs for the approved smoke;
do not create another trial merely to continue this preparation.
[Open the local experiment](http://localhost:3000/trials/56538208-dd78-4922-b760-3ed7264fb424/experiments).

## Scope and approval gate

No infrastructure apply or GPU execution is authorized yet. Proposed single run:

- Existing AWS account `345594603419`, `us-west-2`, `crucible-eks`, namespace/team
  `zipline-default` / `default`, service account `spark-operator-spark`, role
  `crucible-spark-compute-execution`, profile `s6e11-l40s`.
- One On-Demand `g6e.xlarge` / L40S. AWS Pricing API returned **$1.861/hour** on
  November 11, 2026. Offered in both configured AZs; launch capacity unproven.
- `ray.timeout.seconds=3600`: 60 minutes including initialization. KubeRay also
  fails jobs that have not reached Running within 900 seconds. No task/job retries.
  Planning allowance: 5–15 minutes setup, up to 35 minutes training, up to
  10 minutes scoring/checkpoint uploads; these are bounds, **not L40S benchmarks**.
- Terminal RayCluster deletion after 2 minutes, then empty-node consolidation
  after 1 minute. Allow 10 minutes for cleanup: about **$2.18** compute for 70
  minutes. Node expiry at 2 hours with 5-minute termination grace is an independent
  fallback (~**$3.88** compute for 125 minutes). Propose **$5** for this one attempt
  including small EBS/S3 request overhead; no automatic retry or full campaign.
  Retained checkpoint storage continues after compute stops. Controller/API faults
  can delay cleanup; verify actual EC2 termination before declaring completion.

Infrastructure worktree: `/private/tmp/gpt2-crucible-infrastructure`, branch
`codex/gpt2-crucible-l40s`, base `d392916`. Saved plan:
`aws/zipline-orchestration/tfplan-gpt2-scoped`. It creates the GPU NodePool,
NVIDIA device-plugin DaemonSet and one-GPU quota, and updates **only labels** on
`crucible-default`. No CPU fleet/nodeclass/IAM/network changes. The default nodes
had 1.97–3.04 requested CPU cores free and at least 11.7 GiB requested memory free.
The NodePool has no replicas/warm capacity, limits 4 CPU / 32 GiB / 1 GPU and only
permits Linux AMD64 On-Demand `g6e.xlarge`. Namespace quota bounds pending workers
as well as running workers; Karpenter limits alone are eventually consistent.

Reuse `EC2NodeClass/zipline`, NVIDIA AMI `ami-07c57d9a1e75511eb`, release
`al2023@v20260625`, 100-GiB encrypted root disk, existing subnets
`subnet-09dc015f22053f573` / `subnet-073da1661adb53fa3`. AWS's
[release](https://github.com/awslabs/amazon-eks-ami/releases/tag/v20260625) lists
NVIDIA 580.159.03 and toolkit 1.19.1; it also flags an **ENA 2.17.0g reboot risk**.
The shared nodeclass is deliberately not rolled. The
[NVIDIA static plugin v0.17.1](https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.1/deployments/static/nvidia-device-plugin.yml)
is restricted to these workers, with initialization errors enabled. GPU visibility
and driver/image compatibility still require the approved live run. The pinned
PyTorch 2.15 wheel provides CUDA 13.2 (alongside the base image's CUDA 12.8);
[NVIDIA minor compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)
requires driver 580 or later for CUDA 13.x. No `torch.compile`/PTX compilation is
requested; a CPU image test cannot establish GPU compatibility.

The full-state plan hit unrelated Cloudflare credentials and orchestration drift.
Only the following scoped plan is eligible for review; do not apply a full plan:

```sh
cd /private/tmp/gpt2-crucible-infrastructure/aws/zipline-orchestration
export ASDF_OPENTOFU_VERSION=1.12.7
tofu init -backend-config=backend.hcl
tofu validate
tofu plan -var=enable_s6e11_l40s=true \
  -target=aws_eks_node_group.default -target=helm_release.s6e11_l40s \
  -target=kubernetes_daemon_set_v1.s6e11_nvidia_device_plugin \
  -target=kubernetes_resource_quota_v1.s6e11_gpu -out=tfplan-gpt2-scoped
# Only after approval; recheck for labels-only nodegroup change and 3 additions:
tofu apply tfplan-gpt2-scoped
```

Backend: `s3://zipline-crucible-opentofu-state/zipline-orchestration/terraform.tfstate`.
Backend/tfvars/plan files are ignored and may contain secrets; do not commit them.

## Start the existing local stack

Use the prepared Platform worktree, branch `codex/gpt2-crucible-local`. Its only
changes are opt-in Databricks-lookup skip, overridable Hub verticles/kube directory,
and forwarding the execution region. Profile forwarding is already in #1461.
The worktree's fresh `postgres_data` keeps old local workflows and databases intact.
Do not copy an old database into this stack without auditing its active workflows.

```sh
cd /private/tmp/gpt2-crucible-platform
bash setup_subtree.sh
aws sts get-caller-identity
mkdir -p /private/tmp/gpt2-local-kube
aws eks update-kubeconfig --region us-west-2 --name crucible-eks \
  --kubeconfig /private/tmp/gpt2-local-kube/config
export LOCAL_KUBE_DIR=/private/tmp/gpt2-local-kube
export KUBECONFIG="$LOCAL_KUBE_DIR/config" ASDF_KUBECTL_VERSION=1.31.3
kubectl config current-context # Must end in :cluster/crucible-eks
export CUSTOMER_ID=crucible AWS_DEFAULT_REGION=us-west-2 EKS_CLUSTER_NAME=crucible-eks
export CRUCIBLE_RAY_GPU_PROFILES=s6e11-l40s CRUCIBLE_EXECUTION_REGION=us-west-2
export CRUCIBLE_SKIP_DATABRICKS=true
export AWS_HUB_VERTICLES=ai.chronon.hub.AWSOrchestrationVerticle,ai.chronon.hub.AWSWorkflowExecutionVerticle
./docker/orchestration/build_and_start.sh --cloud aws --crucible
```

Wait for `http://localhost:3000` and
`http://localhost:3000/services/hub/healthz`. Never use `down -v` or delete
`postgres_data`. The launcher starts the local UI/Hub/Postgres, not a production
Hub release. Trials and workflow history remain on this laptop.

Use the PR's CLI source plus matching generated Thrift bindings if the globally
installed CLI lacks `hub validate`/`hub workflows`. No package/runtime edits:

```sh
mkdir -p /private/tmp/gpt2-cli-gen
cd /private/tmp/gpt2-crucible-platform
for f in chronon/thrift/*.thrift; do thrift --gen py -out /private/tmp/gpt2-cli-gen "$f"; done
export PYTHONPATH=/private/tmp/gpt2-cli-gen:/private/tmp/gpt2-crucible-platform/python/src
export ASDF_PYTHON_VERSION=3.13.0
cd /private/tmp/gpt2-crucible-demo/training/gpt2
export CONF_ROOT="$PWD/configs" HUB=http://localhost:3000/services/hub
```

## Prepare, build and publish

CPU tests use the existing modelpg environment read-only (or install this package's
requirements in a separate Python 3.12 environment). Never install ML dependencies
in Chronon. `trainer.data` audits hashes, labels/IDs, saved fold assignments and
exact relational source-overlap exclusion; it never generates splits.

```sh
export GPT2_WEIGHTS=/Users/cristian/meself/modelpg/.cache/models/gpt2
/Users/cristian/meself/modelpg/.venv-gpt/bin/python -m unittest discover -s tests -v
# Use a fresh output directory; initial audited work/data already exists.
/Users/cristian/meself/modelpg/.venv-gpt/bin/python -m trainer.data \
  --competition /Users/cristian/Downloads/playground-series-s6e11 \
  --reference /Users/cristian/meself/modelpg/competitions/playground-series-s6e11 \
  --output work/data-new
mkdir -p work/weights
cp "$GPT2_WEIGHTS"/* work/weights/
REPO=345594603419.dkr.ecr.us-west-2.amazonaws.com/ctr-trainer-ray
TAG="$REPO:s6e11-gpt2-20261111"
docker build --platform linux/amd64 -t "$TAG" .
docker run --rm --platform linux/amd64 -e GPT2_WEIGHTS=/opt/gpt2 \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD:/work:ro" -w /work "$TAG" \
  python -m unittest discover -s tests -v
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin 345594603419.dkr.ecr.us-west-2.amazonaws.com
docker push "$TAG"
IMAGE=$(docker inspect --format '{{index .RepoDigests 0}}' "$TAG")
python3 build_archive.py --image "$IMAGE"
```

The archive implementation is the existing deterministic `build_archive.py`
convention. Code version is the archive SHA256's first 12 characters. The build
writes `manifests/artifacts.json` and `manifests/trainer.json`; the archive contains
only setup metadata and trainer Python sources, never data or checkpoints.
The published digest pins dependencies as well as the model snapshot. Ray's
unused CuPy package is removed because its NumPy constraint conflicts with the
verified pilot. No dependency checks are bypassed.

```sh
aws s3 sync work/data/ s3://zipline-artifacts-crucible/gpt2-s6e11/data/ \
  --exclude dataset.json
aws s3 cp manifests/dataset.json \
  s3://zipline-artifacts-crucible/gpt2-s6e11/manifests/dataset-802675cfd652bea99179b2f47402f906d581969773e3f57e6defca4689fc32ea.json
# Already registered during preparation; inspect before creating, never replace:
aws glue get-table --region us-west-2 --database-name data --name s6e11_gpt2_train_87eaa10b
# On first setup only: aws glue create-table --region us-west-2 --database-name data --table-input file://manifests/glue-table.json
VERSION=$(python3 -c 'import json; print(json.load(open("manifests/artifacts.json"))["trainer_code_version"])')
MANIFEST_URI=$(python3 -c 'import json; print(json.load(open("manifests/artifacts.json"))["trainer_manifest_uri"])')
aws s3 cp "dist/s6e11_gpt2_smoke-$VERSION.zip" "s3://zipline-artifacts-crucible/gpt2-s6e11/builds/s6e11_gpt2_smoke-$VERSION.zip"
aws s3 cp manifests/trainer.json "$MANIFEST_URI"
```

## Compile, attribute, validate and submit

Bootstrap the genuine smoke config, then search/start/resume the trial **before**
any comparison variant or its archive is changed. This first run is only smoke.

```sh
zipline compile --chronon-root "$CONF_ROOT"
CONF="$CONF_ROOT/compiled/models/default/gpt2.smoke__$VERSION"
MODEL="default.gpt2.smoke__$VERSION"
# Read the actual compiler output; it must contain localhost, customer crucible,
# default team, prod compile environment, exactly one worker and the pinned image.
zipline config list --chronon-root "$CONF_ROOT" --env prod
zipline hub trial journal list --run-name s6e11-gpt2-crucible-smoke \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
zipline hub trial list --run-name s6e11-gpt2-crucible-smoke \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
# Start a new trial only when deliberately beginning a new attempt:
# zipline hub trial start s6e11-gpt2-crucible-smoke --task 'One L40S: verified GPT-2 pilot through local Trials' --model "$MODEL" \
#   --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
# For the already prepared trial:
export ZIPLINE_TRIAL_ID=56538208-dd78-4922-b760-3ed7264fb424
# For a genuinely new trial, use its returned ID instead.
export ZIPLINE_EXPERIMENT_ID=pilot-parity-f0-s42
zipline hub validate-table data.s6e11_gpt2_train_87eaa10b --engine-type SPARK --team default \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --validate-url http://localhost:3904 --env prod --no-use-auth -f json
zipline hub validate --skip-compile "$CONF" --chronon-root "$CONF_ROOT" \
  --hub-url "$HUB" --validate-url http://localhost:3904 --no-use-auth -f json
zipline hub trial experiments record "$ZIPLINE_EXPERIMENT_ID" "$ZIPLINE_TRIAL_ID" \
  --title 'FP32 saved 20k/10k pilot, one L40S' --status PLANNED --model-conf-name "$MODEL" \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
# PR #1461's CLI has no params flag; its existing client accepts this metadata.
python - <<'PYMETADATA'
import json, os
from ai.chronon.repo.hub_runner import _trial_hub
from ai.chronon.cli.formatter import Format
hub, _, _ = _trial_hub(os.environ["CONF_ROOT"], os.environ["HUB"], False,
                       Format.JSON, "aws", "crucible", "prod")
hub.call_trial_experiment_record_api(os.environ["ZIPLINE_TRIAL_ID"],
    os.environ["ZIPLINE_EXPERIMENT_ID"], params=json.dumps({
        "variant": "pilot_parity", "fold": 0, "seed": 42, "purpose": "validation"}))
PYMETADATA
# ONLY AFTER APPROVED APPLY/RUN; both IDs must be nonempty:
zipline hub trial experiments record "$ZIPLINE_EXPERIMENT_ID" "$ZIPLINE_TRIAL_ID" --status RUNNING \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID="$ZIPLINE_EXPERIMENT_ID" \
  zipline hub backfill "$CONF" --skip-compile --start-ds 2026-11-11 --end-ds 2026-11-11 \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --no-use-auth --yes -f json
```

`backfill` and `validate` derive cloud/customer/environment from the compiled
conf and explicit compile root/path; they do not have invented `--env` flags.
Commit and push reviewable config changes before Hub sync (the CLI enforces a
clean, pushed branch): `git add training/gpt2 && git commit -m "Prepare GPT-2 smoke"`
and `git push -u origin codex/gpt2-crucible-smoke` from the demo repository root.
The source table is for transport/schema validation; training always consumes
manifest-hashed original CSVs. IDs and ingestion dates are not predictors.

## Inspect, cancel and retrieve

Set `WORKFLOW_ID` from the actual submission response, not a guessed Ray name.

```sh
zipline hub workflows status "$WORKFLOW_ID" --wait --timeout 4200 \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
# To stop:
zipline hub cancel "$WORKFLOW_ID" --chronon-root "$CONF_ROOT" --hub-url "$HUB" \
  --cloud aws --customer-id crucible --env prod --no-use-auth -f json
# Inspect attempts; response includes exact attempt IDs and report artifacts:
curl -fsS "$HUB/trials/v1/$ZIPLINE_TRIAL_ID/experiments/$ZIPLINE_EXPERIMENT_ID/attempts"
# Set ATTEMPT_ID from that response. Each download URL is obtained via:
curl -fsS "$HUB/trials/v1/$ZIPLINE_TRIAL_ID/experiments/$ZIPLINE_EXPERIMENT_ID/attempts/$ATTEMPT_ID/artifacts/validation"
zipline hub trial experiments metrics "$ZIPLINE_EXPERIMENT_ID" "$ZIPLINE_TRIAL_ID" --model-conf-name "$MODEL" \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
zipline hub trial experiments list "$ZIPLINE_TRIAL_ID" \
  --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth -f json
```

Verify actual GPU name/visibility in `profile.json`, progress in local Trials,
report-backed AUC/AP/log loss and row counts, prediction/checkpoint downloads, then
`kubectl get nodes -l karpenter.sh/nodepool=s6e11-l40s` and corresponding EC2 state.
A submitted workflow, stale heartbeat or missing report is not completion.
After inspecting evidence, set the accurate status (not automatic success):

```sh
zipline hub trial summary "$EVIDENCE_SUMMARY" "$ZIPLINE_TRIAL_ID" --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth
zipline hub trial status "$EVIDENCE_STATUS" "$ZIPLINE_TRIAL_ID" --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth
zipline hub trial journal append "$EVIDENCE_SUMMARY" "$ZIPLINE_TRIAL_ID" --chronon-root "$CONF_ROOT" --hub-url "$HUB" --cloud aws --customer-id crucible --env prod --no-use-auth
```

## Resume, full recipe and pooled OOF

Checkpoints contain model/optimizer/CPU+CUDA RNG and next optimizer step; row and
field permutations derive from step/epoch seeds. To resume, use a **new attempt**
and a manifest `resume` object with `parent_attempt_id`, `stage`, `checkpoint_uri`,
`sha256`; set `ZIPLINE_PARENT_ATTEMPT_ID` in that model's execution environment.
The saved `.pt.json` recipe must match exactly for a classifier checkpoint.
A source checkpoint can initialize another fold only when source settings, data,
model, image and code identities match; fold/scoring choices do not affect adaptation. Never reuse the parent's output
root. Scoring can be rerun from a completed competition checkpoint; prior chunks
remain preserved. Reports publish once, after referenced objects are durable.

`presets/reference_small.json` keeps 60 source / 8 competition epochs, source
batch 16 / competition effective batch 32, BF16 and 30 orders configurable. It is
not submitted here. Every future fold/variant needs a distinct backend model and
compiled identity and a real trial/experiment before publication. This port retains
the pilot's token-weighted AdamW semantics; it does not claim exact legacy GReaT
optimizer parity. Scoring uses FP32 transformer/head and float64 likelihood sums;
30 orders use log-sum-exp of likelihoods, not mean probabilities. Prior policies
are explicit. No tree comparison is emitted unless evaluated on identical IDs.

For five **complete**, compatible full-fold prediction files and their `.json`
sidecars (sampled smoke files are rejected):

```sh
python -m trainer.aggregate --truth /path/to/original/train.csv \
  --folds /path/to/persisted/folds.csv --output work/oof-report.json \
  /path/f0/validation.csv /path/f1/validation.csv /path/f2/validation.csv \
  /path/f3/validation.csv /path/f4/validation.csv
```

The aggregator validates one held-out prediction per training ID, matching labels,
fold membership, checksums and recipe/image/code provenance, then reports pooled
`oof_auc`, `oof_average_precision`, `oof_logloss`. Mean fold AUC is not pooled AUC.
