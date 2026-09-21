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

## 6. Failure analysis

```bash
harbor analyze <job-dir> -m sonnet -r .tb3/docs/prompts/trial-analysis.toml \
  --job-prompt .tb3/docs/prompts/trial-analysis-job.txt
```

__pending__
