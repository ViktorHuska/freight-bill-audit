# Results

Every command below was run from the repository root on Windows 11 with Docker
Desktop 28.4.0 (Linux containers, 20 CPUs / 31 GB), using the local `docker`
backend. Harbor 0.23.0, installed with `uv tool install harbor`.

| | |
|---|---|
| Task version evaluated | commit `f112776` (task files unchanged since; later commits touch `scripts/` and docs only) |
| TB3 checks and prompts | `harbor-framework/terminal-bench` @ `2e5fd44` |
| CI defaults mirrored | `.github/harbor-run-defaults.yml` at that commit: 3 trials per agent; claude-code `anthropic/claude-opus-5`, `reasoning_effort=max`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`; codex `openai/gpt-5.6-sol`, `reasoning_effort=xhigh` |

## 1. Static checks

```bash
bash scripts/run_checks.sh
```

**25 / 25 pass.** The runner clones the TB3 repo into `.tb3/` and runs every
`scripts/checks/check-*.sh` against `tasks/freight-bill-audit`, as CI does.

One note for anyone reproducing this on a path containing a space: the
upstream checks word-split their arguments, so an absolute path such as
`.../Klavis AI/...` splits into two nonexistent task dirs and several checks
pass *vacuously*. `run_checks.sh` passes a relative path from the repo root to
avoid that; the results above come from that run.

## 2. Implementation rubric

```bash
harbor check tasks/freight-bill-audit -r .tb3/docs/prompts/task-implementation.toml
```

Result: __pending__

## 3. Oracle and nop

```bash
harbor run -p tasks/freight-bill-audit --agent oracle --env docker --yes
harbor run -p tasks/freight-bill-audit --agent nop    --env docker --yes
```

| Agent | Reward | Runtime | Job |
|---|---|---|---|
| oracle | **1.000** | 1 m 48 s | `jobs/2026-09-21__00-01-22` |
| nop | **0.000** | 35 s | `jobs/2026-09-21__00-03-55` |

The oracle run covers the whole pipeline: `solve.sh` installs the reference
tool and runs it on batch A in the agent container, then the separate verifier
runs that same tool on hidden batch B as the unprivileged `auditrun` user and
grades both batches.

### Independent cross-check of ground truth

Ground truth is computed twice, by code that shares nothing: the generator
(`tools/generator/`, at planting time) and the reference solution
(`solution/audit.py`, from `policy.md` alone). Diffing them field by field:

| Batch | Invoices | Lines | Sales orders | Result |
|---|---|---|---|---|
| A | 11 | 85 (24 disputed) | 32 | identical: every status, match, billed / expected / variance, decision, reason, and landed-cost cell |
| B | 11 | 85 (24 disputed) | 32 | identical |

Regenerating a batch reproduces every data file, truth file and PDF byte for
byte.

## 4. Standard trials

```bash
N_CONCURRENT=3 bash scripts/trials.sh codex
N_CONCURRENT=2 bash scripts/trials.sh claude     # CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token`
```

`trials.sh` runs `harbor run -k 3` with the CI agent/model/kwargs above. Codex
authenticates from `~/.codex/auth.json` (`CODEX_FORCE_AUTH_JSON=1`).

| Agent | Trial | Reward | Wall time | Genuine / infra | Failing tests |
|---|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 1 | | | | |
| codex gpt-5.6-sol xhigh | 2 | | | | |
| codex gpt-5.6-sol xhigh | 3 | | | | |
| claude-code opus-5 max | 1 | | | | |
| claude-code opus-5 max | 2 | | | | |
| claude-code opus-5 max | 3 | | | | |

Jobs: `jobs/2026-09-21__00-52-12-codex`, `jobs/2026-09-21__00-52-15-claude`.

Trials rerun because of infrastructure failures (rate limit, crash, timeout): __

## 5. Adversarial trials (`/cheat`)

```bash
CHEAT=1 bash scripts/trials.sh codex
CHEAT=1 bash scripts/trials.sh claude
```

As in `run-cheat-trials.yml`, `docs/prompts/hack-trial-prompt.md` is
**appended** to the instruction in a throwaway copy of the task, and one trial
runs per agent.

| Agent | Reward | What the agent attempted | Why it scored 0 |
|---|---|---|---|
| codex | | | |
| claude-code | | | |

## Iteration history

### Iteration 1: task v2 (source precedence) @ `f112776`, 2026-09-21

| Agent | Trials | Reward | Wall time | Job |
|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 3 | **1.0 / 1.0 / 1.0** (38/38 tests each, including hidden batch B) | 19 min for the whole job, 3 in parallel | `jobs/2026-09-21__00-52-12-codex` |
| claude-code opus-5 max | 3 | __running__ | | `jobs/2026-09-21__00-52-15-claude` |

**These are genuine passes.** Each agent's own `audit.py` ran on the hidden
batch B in the verifier (exit 0) and matched the truth on every field. The
truth never exists in the agent container.

**What the trajectory shows (codex, `ptkAW7D`).** The agent ran **10 shell
commands** in total:
1. Listed `/app/data` and read `policy.md`.
2. Dumped every JSON/CSV file and extracted every PDF with `pdftotext`.
3. Wrote a ~900-line `audit.py` in essentially one pass.
4. Ran it once and checked its own reconciliation, then stopped.

After reading the data it named every trap in one sentence: *"a revised
sailing changes contract version and FX date, one container is reassigned
between bookings, terminal weighbridge weight overrides ERP weight, two
tariff circulars override selected rates, detention…"*

**Diagnosis.** v2 moved the difficulty from "rules stated in bold" to "sources
that disagree", but it is still a **read-and-solve** task, which TB3's
contributing guide names as the opposite of what makes tasks hard:

1. **The policy is a complete algorithm.** The §2 precedence table says
   exactly which source wins for each fact, so "conflicting evidence"
   reduces to another rule to translate. In the merged Operations tasks,
   precedence requires judgment across a rich environment; here it is a
   lookup.
2. **Everything is visible at once.** About 15 small files that fit in one
   context. There is nothing to explore, no feedback loop, and no reason to
   iterate.
3. **Generalising is free.** Batch B has the same structure, and clean text
   PDFs make the parsers straightforward.

Adding traps, rules, invoices or precision would not change this. It is
still read-and-solve, and that kind of difficulty is exactly what
`essential_difficulty` rejects.

## 6. Failure analysis

```bash
harbor analyze <job-dir> -m sonnet -r .tb3/docs/prompts/trial-analysis.toml \
  --job-prompt .tb3/docs/prompts/trial-analysis-job.txt
```

__pending__
