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
`manifests/verification.json`; the subsequent A10G execution results are below.

The existing local trial is `56538208-dd78-4922-b760-3ed7264fb424`, experiment
`pilot-parity-f0-s42` (**FAILED before training: AWS capacity unavailable**).
These IDs identify the completed first attempt. The requested g5 retry is recorded
as `pilot-g5-f0-s42` in the same trial.
[Open the local experiment](http://localhost:3000/trials/56538208-dd78-4922-b760-3ed7264fb424/experiments).

## Execution outcome

The user approved the scoped apply and one attempt on November 11, 2026. Apply
completed with **3 additions, 1 labels-only update, 0 deletions**. Workflow
`180fd741-e59f-42f9-ad0f-69a6450aeb66` failed before training: AWS repeatedly
returned `InsufficientInstanceCapacity` for `g6e.xlarge` in both configured AZs.
The CPU head became ready, but **zero GPU instances launched**. KubeRay enforced
`PreRunningDeadlineExceeded` at **20:56:10 UTC**, following its 900-second startup
bound. Automatic cleanup was verified at **20:58:48 UTC**: no RayCluster, job pods,
GPU nodes or NodeClaims; GPU quota usage returned to 0/1.

Only `run_context.json` exists under this attempt's S3 root. No trainer progress,
report, checkpoint, predictions or new metrics were produced. Trial/experiment
status was FAILED and the journal records the capacity failure. See
`manifests/execution.json` for exact identities and AWS errors. GPU execution and
artifact/report verification remained untested after this first attempt. The user
subsequently requested the g5 retry described below.

## Requested g5 retry

On November 11 the user requested one `g5.xlarge` retry under the same $5,
900-second startup and 3600-second job bounds. AWS pricing returned $1.006/hour
in us-west-2. This is one A10G (24 GB GPU memory), 4 vCPU and 16 GiB host RAM.
The existing `s6e11-l40s` profile name is retained for compatibility; its current
instance selection is g5, not L40S. Only its instance requirement and memory
limit changed (0 add, 1 change, 0 destroy); the previous default remains g6e.
The isolated team's current worker requests are 12 GiB RAM and 4 GiB shared
memory, so recompiling either smoke model uses that host sizing.

Variant `default.gpt2_g5.smoke__914323868f4f` / backend
`s6e11_gpt2_smoke_g5` uses `manifests/trainer-g5.json`: microbatch 4,
accumulation 8 in both stages (effective batch 32), scoring batch 4, otherwise
the same FP32 pilot/data/weights. It reuses the pinned image and byte-identical
trainer archive, copied under the new backend name. Compilation and local
training-data validation passed. The live GPU run subsequently succeeded.

Applied scoped infrastructure command:

```sh
tofu plan -var=enable_s6e11_l40s=true -var=s6e11_instance_type=g5.xlarge \
  -target=helm_release.s6e11_l40s -out=tfplan-gpt2-g5
tofu apply tfplan-gpt2-g5
```

For this variant the compile/validate/record/submit commands below use
`MODEL=default.gpt2_g5.smoke__914323868f4f`,
`CONF="$CONF_ROOT/compiled/models/default/gpt2_g5.smoke__914323868f4f"`, and
`ZIPLINE_EXPERIMENT_ID=pilot-g5-f0-s42`, with the same trial ID. Publish
`trainer-g5.json` to the content-addressed URI in `artifacts-g5.json`, and copy
the existing archive to `builds/s6e11_gpt2_smoke_g5-914323868f4f.zip`.
Do not rerun an already submitted paid attempt without new authorization.

The initial local submission `b640af0e-7149-4e24-8e4c-a8476699a773` was rejected
before creating a RayJob because the experiment model association was missing.
The association was corrected using the CLI's `--model-conf-name` argument;
actual workflow: `b5c3173a-5811-4fd6-b41a-6b89e8f880a0`.

**Result: SUCCEEDED**, 21:48:46–22:10:46 UTC (22 minutes including startup).
AWS launched instance `i-02a39cbed6e5afef7` in `us-west-2a` at 21:48:51 UTC.
Actual NVIDIA A10G/driver 580.159.03 verified; peak allocated GPU memory was
3.320 GiB. Source and competition stages each completed 625 optimizer steps,
20,000 rows and effective batch 32. Their measured stage times including
checkpoint handling were 445.13 and 444.57 seconds respectively.

On the saved **10,000-row fold-0 sample**: ROC-AUC **0.7422719901**,
average precision **0.1756680123**, log loss **0.0729153785**. Exact unique
validation-ID coverage, prediction-file SHA256 and independent metric
recomputation all passed. This is sampled validation, not full-fold or pooled
OOF performance. Local Trials ingested fresh progress, the final checkpoint,
and the final report (`execution_state=success`, `evaluation_state=valid`).
All seven report artifacts exist in S3. See `manifests/report-g5.json`,
`manifests/profile-g5.json`, and `manifests/execution-g5.json`.

Artifact root:
`s3://zipline-artifacts-crucible/gpt2-s6e11/runs/b5c3173a-5811-4fd6-b41a-6b89e8f880a0/c76921e0-956f-4161-8a44-232b27020381/1/`.
Final resumable checkpoint: `checkpoints/competition-00000625.pt`;
predictions: `predictions/validation.csv`; report: `experiment_report.json`.
GPU checkpoint publication was verified; an interrupted live GPU resume was
not executed (resume correctness has CPU test coverage).

Automatic RayCluster deletion released GPU quota to 0/1. Karpenter selected the
empty node for deletion at 22:14:10 UTC and EC2 entered shutting-down at
22:14:16 UTC, with no replacement. From launch to shutdown initiation was
25m25s, approximately **$0.43 EC2 compute** at the quoted rate (estimate,
excluding EBS/S3/network and existing shared CPU infrastructure). The completed
CPU submitter pod and RayJob record can remain as status history; they hold no
running GPU allocation. EC2 `terminated` and zero GPU nodes/NodeClaims were
verified at **22:19:37 UTC**. The profile remains installed at zero capacity.

AWS's [real-time capacity scores](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-manager-supportability.html)
require the Unified Operations support plan and enabled EC2 Capacity Manager.
Our read-only check for one g5/g6e across the existing AZs returned
`CapacityManager.Disabled`. No account-wide service was enabled. Scores are
advisory, not reservations or launch guarantees. Instance-type offerings only
show supported locations; API DryRun checks permissions, not free capacity.

## Short BF16 throughput benchmark

Requested after the FP32 cost estimate, under the same one-GPU, 900-second
startup / 3600-second job / $5 bounds. Experiment
`benchmark-bf16-g5-f0-s42` in trial `56538208-dd78-4922-b760-3ed7264fb424`,
workflow `aef6529f-9bea-44e9-8154-9c036cc66db6`, model
`default.gpt2_bf16_g5.smoke__914323868f4f`, backend
`s6e11_gpt2_benchmark_bf16_g5`. The unchanged image and trainer bytes are reused.

Preset `benchmark_bf16_g5.json` uses the same saved 20k source / 20k training /
10k validation rows, one epoch per training stage, BF16 autocast, microbatch 16,
source accumulation 1 (effective 16), competition accumulation 2 (effective 32),
score batch 8, three orders, and the reference no-prior scoring policy. Scoring
itself remains FP32. `checkpoint_steps=10000` saves only the final checkpoint of
each short stage. These changes measure the proposed recipe settings together,
not an isolated precision-only speedup or a predictive-quality comparison.

Manifest: `manifests/trainer-bf16-g5.json`, with immutable URI/hash in
`manifests/artifacts-bf16-g5.json`. Compilation and local training-data validation
passed. The larger full-fold data and 30-order runtime remain projections; this
benchmark does not establish full-fold host-memory fit or authorize five folds.

**Result: SUCCEEDED**, 22:26:31–22:45:23 UTC (18m52s including startup).
Native BF16 support was confirmed on the actual A10G, driver 580.159.03.
Sustained rates after the first 100 optimizer steps were **84.18 source rows/s**
and **89.33 competition rows/s**. The earlier FP32 configuration measured about
53.01 rows/s after excluding checkpoint pauses: improvements of **1.59x** and
**1.68x** for the respective settings. Source/competition compute took 238.13 /
223.78 seconds; stage times including final checkpoint handling were 254.56 /
240.18 seconds. Peak allocated GPU memory was **6.929 GiB**. Scoring remained
FP32 and took **315.37 seconds** for 10,000 rows × three orders × both labels,
including evaluation-artifact publication: **95.13 row-orders/s**.

Projection for the complete reference recipe on one sequential g5, reusing the
60-epoch source checkpoint across folds:

| Component | Projected GPU hours |
| --- | ---: |
| 20k source rows × 60 epochs, batch 16 | 3.96 |
| 559,968 training rows × 8 epochs × 5 folds, batch 32 | 69.65 |
| 699,960 held-out rows × 30 orders, both labels | 61.32 |
| Checkpoint overhead, assuming every 10,000 steps | 0.36 |
| **Total** | **135.29 (5.64 days), $136.10 EC2 compute** |

The checkpoint assumption means approximately 78 saves across source plus five
folds, not the full preset's current every-200-step policy. This projection does
not modify or launch that full preset. Use a **15–25% planning allowance**:
155.6–169.1 hours (6.5–7 days), **$157–170 compute** at $1.006/hour. Storage,
network, existing shared CPU infrastructure, arbitrary retries and capacity
waiting are excluded. Full 30-order test predictions from all five models would
add approximately 131.4 GPU hours / $132 compute. The full-fold memory probe
below subsequently verified fold-0 memory fit.
Long-run behavior remains untested; the three-order scoring measurement is
extrapolated linearly to 30 orders.

All seven report artifacts exist, and exact unique held-out IDs, checksum, and
independent metric recomputation passed. Local Trials reports success/valid.
The report contains AUC 0.8090738080, AP 0.1958911760, log loss 0.6140867647.
These are not a controlled quality comparison with the earlier pilot: precision,
batches, prior policy and scoring order count changed. See
`manifests/execution-bf16-g5.json`, `manifests/profile-bf16-g5.json`,
`manifests/report-bf16-g5.json` and `manifests/projection-bf16-g5.json`.

Artifact root:
`s3://zipline-artifacts-crucible/gpt2-s6e11/runs/aef6529f-9bea-44e9-8154-9c036cc66db6/0abbe3f1-f3ef-4c45-bec4-35fdfe483f03/1/`.
Automatic RayCluster cleanup released GPU quota to 0/1. The instance
`i-0d0aeac2c89d680cf` launched at 22:26:36 UTC and entered shutting-down at
22:48:54 UTC, giving an estimated **$0.37 EC2 compute** before other charges.
EC2 `terminated` and zero GPU nodes/NodeClaims were verified at **22:54:05 UTC**.

## Full fold-0 memory probe

The user requested a bounded memory-fit check before any full campaign.
Model `default.gpt2_memory_g5.smoke__a16f67c8dd50`, backend
`s6e11_gpt2_memory_g5`, experiment `memory-fullfold-g5-f0-s42` in the same trial.
The dedicated `trainer.memory_probe` entrypoint reuses the existing dataset
loader, RowEncoder, train_stage, checkpoint writer and likelihood scorer.
Its new archive version is `a16f67c8dd50`; the training image is unchanged.

The probe loads 20,000 source rows, all 559,968 fold-0 training rows and 139,992
held-out rows; all three full encoders remain resident. It selects long encoded
rows for 20 source steps (batch 16) and 20 competition steps (batch 32) using
BF16/microbatch 16. Both stages exercise AdamW allocation and checkpoint writing.
Eight long validation rows are scored with both labels across 30 feature orders
in FP32. Two resident full-fold likelihood arrays model accumulation and
concatenation memory for 30-order evaluation. This is a memory test, not a full
epoch, full validation evaluation, or predictive-quality comparison.

Kernel cgroup current/peak/limit and OOM counters are recorded alongside process
RSS and CUDA allocated/reserved peaks. Progress is published before and after
loading/encoding/training/scoring so failures can be localized. A successful
report contains memory measurements only, with no fabricated AUC or predictions.
The one-GPU quota, 12 GiB worker limit, 900-second startup and 3600-second job
bounds are unchanged. No infrastructure apply is needed.

Native and AMD64-image CPU suites each passed all 14 tests, including exact
long-row length bounds across feature orders and selected-row mapping. The
compiled model passed local training-data validation. Both manifest and archive
are immutable and referenced by `manifests/artifacts-memory-g5.json`.

**Result: SUCCEEDED**, 23:01:15–23:10:16 UTC (9m01s including startup;
77 seconds for the Ray driver). An initial capacity rejection was followed by
successful placement in us-west-2a within the same bounded attempt.
All full-fold frames/encoders remained resident while both 20-step stages,
checkpoint saves and 30-order scoring completed. Kernel OOM counters stayed zero.

| Memory measurement | Observed peak | Available limit |
| --- | ---: | ---: |
| Worker host memory, kernel cgroup including transient allocations | 5.150 GiB | 12 GiB |
| CUDA tensor allocation | 6.985 GiB | 22.488 GiB visible GPU memory |
| CUDA reserved allocator memory | 8.826 GiB | 22.488 GiB visible GPU memory |

Host headroom was **6.850 GiB (57.1%)**; peak process RSS was 3.148 GiB.
The conservative per-row token-length bounds were source 231, competition 232,
validation 231. The scoring buffer pair occupied 134,392,320 bytes. This supports
memory fit for the tested fold/settings, not full five-fold or multi-day stability.
It does not change the prior runtime projection or start a full campaign.

Workflow `0a17e253-96a6-4ce2-a3be-79f5366a2150`; local Trials reports success/valid.
The saved report was compared with the Hub report, dimensions/step counts/peaks
were independently checked, and both reported S3 artifacts were retrieved.
Dataset SHA-256 matches the immutable manifest. Evidence:
`manifests/report-memory-g5.json`, `manifests/profile-memory-g5.json`,
`manifests/execution-memory-g5.json`.

Artifact root:
`s3://zipline-artifacts-crucible/gpt2-s6e11/runs/0a17e253-96a6-4ce2-a3be-79f5366a2150/afdd78a3-c3e4-42b4-b66d-b2aa2d09ef54/1/`.

Automatic cleanup deleted the RayCluster and released GPU quota to 0/1.
Instance `i-00496b9840beece65` launched at 23:04:29 UTC and entered shutting-down
at 23:13:40 UTC: approximately **$0.154 EC2 compute** (551 seconds), excluding
storage/network/shared CPU charges. EC2 `terminated`, zero GPU nodes/NodeClaims
and device-plugin desired count zero were verified at **23:19:19 UTC**.

To rebuild this variant without changing older variants' manifest files:

```sh
# From training/gpt2, after an intentional probe-code change:
python - <<'PYMEMORY'
import hashlib, json
from pathlib import Path
from build_archive import _archive_bytes
archive = Path("dist/memory-probe.building.zip")
_archive_bytes(archive)
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
version = sha[:12]
archive.rename(Path("dist") / f"s6e11_gpt2_memory_g5-{version}.zip")
manifest_path = Path("manifests/trainer-memory-g5.json")
manifest = json.loads(manifest_path.read_text())
manifest["trainer_code_version"] = version
raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
manifest_path.write_bytes(raw)
msha = hashlib.sha256(raw).hexdigest()
a_path = Path("manifests/artifacts-memory-g5.json")
a = json.loads(a_path.read_text())
a.update(trainer_code_version=version, archive_sha256=sha,
         trainer_manifest_sha256=msha,
         trainer_manifest_uri=f"s3://zipline-artifacts-crucible/gpt2-s6e11/manifests/trainer-{msha}.json")
a_path.write_text(json.dumps(a, sort_keys=True, indent=2) + "\n")
PYMEMORY
```

Then follow the compile/validate/publish/record/submit cycle below with this model,
archive, manifest and experiment identity. Any new paid attempt needs its own
bounded authorization. Kernel accounting and short-step success establish only
observed fold-0 memory fit; they do not establish multi-day leak-free execution.

## Full fold 0 on g5.xlarge

**FAILED at the Hub's separate six-hour step watchdog.** No full-fold validation
metrics were produced. The 42-hour Kubernetes deadline and 44-hour node expiry
were correctly configured, but `StepTracker.scala:39` still sets
`STEP_TIMEOUT_DURATION = Duration.ofHours(6)` for non-continuous workflow steps.
At 06:11:29 UTC on November 12, Hub logged the timeout and killed the running
RayJob; step status changed to timeout at 06:11:30 UTC. This was an orchestration
timeout, not observed GPU or host-memory exhaustion. The earlier preflight tested
request validation and Kubernetes deadlines but missed this separate watchdog.
Do not resubmit the command below until that watchdog path has been corrected
and tested against the configured training deadline.

Automatic cleanup is verified: RayCluster deleted, GPU quota 0/1, zero GPU
nodes/NodeClaims and EC2 `terminated` at **2026-11-12 06:18:35 UTC**.
The instance entered shutting-down at 06:12:57 UTC, after 21,685 seconds
from launch: approximately **$6.06 EC2 compute**, excluding storage/network
and shared CPU charges. The failed job elapsed 21,617 seconds.

Source adaptation completed all **60 epochs / 75,000 steps** in 14,379.73 seconds;
its final checkpoint remains in S3 as `checkpoints/source-00075000.pt`.
Classifier training reached step **19,234/139,992** before termination. The latest
durable classifier checkpoint is `checkpoints/competition-00010000.pt`, containing
model/AdamW state, CPU/CUDA RNG and `next_step=10000`, verified with a safe CPU load.
Downloaded checkpoint SHA-256:
`8b5c8d511a4dc70627cd95bd1f82b5af94743eadf71c3ea0ab7c489d972686a4`.
Resumption from it preserves the completed source adaptation and 10,000 classifier
steps; approximately 9,234 later classifier steps must be repeated.

Smallest recovery: make the Hub's training-step watchdog honor the bounded
configured training timeout, preserve the existing default for unrelated jobs,
and add a test covering this watchdog as well as the Kubernetes deadline. Then
use an explicitly authorized new attempt with the original recipe/code/image,
parent-attempt provenance and verified classifier checkpoint. Neither a replacement
run nor the other four folds has been submitted. No watchdog change was applied
by the monitor. Evidence is in `manifests/execution-fullfold-g5.json` and
`manifests/source-profile-fullfold-g5.json`.


Requested after the successful memory probe. New model
`default.gpt2_fullfold_g5.full_fold__914323868f4f`, backend
`s6e11_gpt2_fullfold0_g5`, experiment `fullfold-bf16-g5-f0-s42`.
The existing BF16 trainer/image are unchanged. The manifest
`manifests/trainer-fullfold-g5.json` selects all fold-0 rows, 60 source epochs,
eight classifier epochs, microbatch 16, effective source/classifier batches
16/32, BF16, and 30-order FP32 validation with `reference_no_prior`.
Checkpoints every 10,000 optimizer steps and stage end are uploaded to the new
attempt root; the completed source checkpoint can be reused for later folds.

Measured-rate projection: approximately 30.25 hours plus checkpoint/startup
costs; allow roughly 35–38 hours / $35–38 EC2 compute at $1.006/hour.
The proposed job cutoff is 42 hours ($42.25 compute before cleanup/storage/network),
with a 15-minute startup limit, no automatic training retry, one-GPU quota and
44-hour node-expiry fallback. Empty nodes still terminate automatically.
Only this model overrides the smoke timeout. The other four folds are not queued.

The user approved the runtime exception and this single full fold. Platform
commit `4873822ea` retains the six-hour default and permits an explicit local
maximum up to 48 hours, forwarded through Compose. The selected override is
`CRUCIBLE_RAY_TIMEOUT_MAX_SECONDS=151200`. Four resource/deadline tests passed
with the default environment and again with the 42-hour opt-in; these exercise
request validation and actual rendered active/startup deadlines.
The new model compiled and passed local training-data validation. Trainer/archive
and manifest were published to the isolated S3 prefix and hash-verified.
The infrastructure variant adds `s6e11_node_expire_hours` (default 2, maximum 48),
with 44 selected only in the targeted full-fold plan. OpenTofu validation passed;
plan `tfplan-gpt2-fullfold` contains exactly one in-place Helm release update.
Decoded before/after values differ only in `expireAfter: 2h` to `44h`.
That plan was refreshed, verified and applied: 0 added, 1 changed, 0 destroyed.
Live NodePool expiry is 44h; its 5-minute termination grace, one-GPU quota and
empty-node cleanup remain unchanged. Infrastructure commit `e123af0`.

The local stack is rebuilt with the override. Record this experiment before
submitting, with both trial and experiment IDs:

```sh
ZIPLINE_TRIAL_ID=56538208-dd78-4922-b760-3ed7264fb424 \
ZIPLINE_EXPERIMENT_ID=fullfold-bf16-g5-f0-s42 \
  zipline hub backfill "$CONF_ROOT/compiled/models/default/gpt2_fullfold_g5.full_fold__914323868f4f" \
  --skip-compile --start-ds 2026-11-11 --end-ds 2026-11-11 \
  --chronon-root "$CONF_ROOT" --hub-url http://localhost:3000/services/hub --no-use-auth --yes -f json
```

Historical launch: submitted November 12 at 00:11:27 UTC; source training started
at 00:16:46 UTC (November 11, 16:16 PST). Workflow
`c5cff551-ce43-415c-8694-e9570397142a`, attempt
`bd0d19bf-c194-4334-8c18-cff5617acbd1-1`, RayJob
`training-fc54568e-7125-3d98-a81f-61cb8e083bd6`.
The actual g5.xlarge instance `i-05ccaea6db4ef5546` is in us-west-2a,
with NVIDIA A10G, driver 580.159.03 and 23,028 MiB visible GPU memory.
Initial training reached source step 322/75,000 with durable S3 progress;
classifier training is configured for 139,992 optimizer steps. Early allocated
GPU memory was 6.505 GiB. These are startup observations, not final metrics.

Artifact root:
`s3://zipline-artifacts-crucible/gpt2-s6e11/runs/c5cff551-ce43-415c-8694-e9570397142a/bd0d19bf-c194-4334-8c18-cff5617acbd1/1/`.
Configured Kubernetes job deadline was **2026-11-13 18:11:27 UTC**
(10:11:27 PST); the separate Hub watchdog terminated it earlier.
Execution evidence: `manifests/execution-fullfold-g5.json`.
Heartbeat `review-gpt-2-fold-0` was removed after this failed attempt and cleanup
were verified. No replacement attempt or other fold was submitted.
Remote runtime deadlines and cleanup do not depend on the laptop staying awake;
local Hub/heartbeat observation requires the local services and app to be available.

Review the actual full validation report, exact 139,992 held-out IDs, independent
AUC/AP/log-loss recomputation, loss/time profiles and durable checkpoints before
considering the other four folds. Close out with the experiment-list,
summary/status/journal commands below only after measured results and cleanup.

## Approved scope and runtime bounds

The following bounds describe the approved first attempt:

- Existing AWS account `345594603419`, `us-west-2`, `crucible-eks`, namespace/team
  `zipline-default` / `default`, service account `spark-operator-spark`, role
  `crucible-spark-compute-execution`, profile `s6e11-l40s`.
- One On-Demand `g6e.xlarge` / L40S. AWS Pricing API returned **$1.861/hour** on
  November 11, 2026. Offered in both configured AZs; actual launches failed for lack of capacity.
- `ray.timeout.seconds=3600`: 60 minutes including initialization. KubeRay also
  fails jobs that have not reached Running within 900 seconds. No task/job retries.
  Planning allowance: 5–15 minutes setup, up to 35 minutes training, up to
  10 minutes scoring/checkpoint uploads; these are bounds, **not L40S benchmarks**.
- Terminal RayCluster deletion after 2 minutes, then empty-node consolidation
  after 1 minute. Allow 10 minutes for cleanup: about **$2.18** compute for 70
  minutes. Node expiry at 2 hours with 5-minute termination grace is an independent
  fallback (~**$3.88** compute for 125 minutes). Approved **$5** for this one attempt
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
launcher changes are opt-in Databricks-lookup skip, overridable Hub verticles/kube
directory, and forwarding the execution region. The separately approved bounded
runtime override is described above. Profile forwarding is already in #1461.
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
# Required only for the approved full-fold run; omit to retain the 6h ceiling.
export CRUCIBLE_RAY_TIMEOUT_MAX_SECONDS=151200
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
# Historical trial/experiment IDs; only resubmit under a new bounded authorization:
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
# Attempt-scoped reports reconcile automatically; do not use the legacy
# `trial experiments metrics` attachment command (it returns HTTP 400 here).
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
