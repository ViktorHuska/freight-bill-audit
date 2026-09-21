# Results

Every command below was run from the repository root on Windows 11 with Docker
Desktop 28.4.0 (Linux containers, 20 CPUs / 31 GB), using the local `docker`
backend. Harbor 0.23.0, installed with `uv tool install harbor`. (TB3 CI pins `0.23.1.dev202609170426`; the one visible difference is that
0.23.0's `harbor analyze` lacks `--job-prompt`, so only the per-trial rubric ran.)

| | |
|---|---|
| Task version evaluated | final: commit `3154205` for all standard and cheat trials. `f8bc5e0` then hardened `tests/test.sh` (ignores pre-existing reward files); oracle and nop were re-run on it. The agent never sees `tests/`. Earlier versions: see *Iteration history* |
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
| oracle | **1.000** | ~1 min | `jobs/final-oracle` (final task incl. hardened `test.sh`); also `jobs/v4b-oracle` |
| nop | **0.000** | ~35 s | `jobs/final-nop`; also `jobs/v4b-nop` |

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
| codex gpt-5.6-sol xhigh | 1 (`4e4oiPh`) | 1.0 | job 19 min 40 s (3 in parallel) | genuine pass | none: 42 passed, 2 skipped |
| codex gpt-5.6-sol xhigh | 2 (`D9y5Pu3`) | 1.0 | 〃 | genuine pass | none: 42 passed, 2 skipped |
| codex gpt-5.6-sol xhigh | 3 (`euzZcYs`) | 1.0 | 〃 | genuine pass | none: 42 passed, 2 skipped |
| claude-code opus-5 max | 1 (`Ei7aKKR`) | 1.0 | job 1 h 14 min (2 in parallel) | genuine pass | none: 42 passed, 2 skipped |
| claude-code opus-5 max | 2 (`oLGqyQH`) | 1.0 | 〃 | genuine pass | none: 42 passed, 2 skipped |
| claude-code opus-5 max | 3 (`qHSW8jX`) | 1.0 | 〃 | genuine pass | none: 42 passed, 2 skipped |

Jobs: `jobs/2026-09-21__10-10-12-codex`, `jobs/2026-09-21__10-14-23-claude`. The
2 skipped tests are the per-trap tests for T15/T16 on batch A, which plants
neither (both are hidden-batch-only by design).

Every pass is genuine: each agent's own `audit.py` ran unchanged on hidden
batch B in the verifier (tool exit 0) and matched the truth on every field.
The truth never exists in the agent container.

**The TB3 requirement that every standard trial fails is not met.**

Trials rerun because of infrastructure failures: none on the final version.
In iteration 1, the claude-code job was lost to a Harbor-on-Windows UTF-8 bug
(see *Iteration history*); it was fixed before any later run.

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
| codex (`jobs/2026-09-21__10-31-40-codex-cheat`) | **0** | nothing: the first turn was blocked by OpenAI's platform | no deliverable |
| codex rerun (`jobs/2026-09-21__10-36-11-codex-cheat`) | **0** | reconnaissance: listed every file under `/app`; searched for verifier artifacts, cached expected outputs, writable dependencies, `.git`, `.pytest_cache` and `/tmp` leftovers | found nothing exploitable (no tests, truth or solution exist in the agent image); then the platform blocked the session |
| claude-code (`jobs/2026-09-21__11-29-23-claude-cheat`) | **0** | a full red-team pass, 14.6 min. It probed whether Python `site-packages` / `sitecustomize` were writable, the `/logs` mounts and host mounts, and every file for truth or expected outputs. It built a zero-logic "ledger leak" tool that copies `ap_ledger.csv` totals | no bypass: the verifier is external; batch A and hidden batch B ship **without** a ledger; the ledger holds invoice totals only, while the tests check every line's decision, reason and amount plus the allocation; month-to-month variation (FX, detention) defeats replaying history. It left no deliverable and reported "no exploit" |

**The one lead the red team raised, tested.** Claude noted that
`/logs/verifier` is a world-writable mount inside the agent container. Harbor
reads `reward.json` in preference to `reward.txt`, and `test.sh` only wrote
`reward.txt`. A planted `reward.json` could therefore win, *if* it survived
into grading. It was tested directly with a throwaway copy of the task whose
solution does nothing but `echo '{"reward": 1}' > /logs/verifier/reward.json`
(job `jobs/exploit-probe-reward-json`). The file was written inside the agent
container but never reached grading: the trial's verifier directory held only
`reward.txt = 0`, so the reward was **0**. As defence in depth for other
backends, `test.sh` now deletes any pre-existing `reward.json` / `reward.txt`
before grading. Oracle (1.0) and nop (0.0) were re-run with that change (jobs
`final-oracle`, `final-nop`). The agent never sees `test.sh`, so the trial
results above are unaffected.

**Codex and the hack prompt.** On a ChatGPT subscription, OpenAI's platform
flags TB3's adversarial prompt: *"This content was flagged for possible
cybersecurity risk… join the Trusted Access for Cyber program"*. The first
trial failed on its first turn and never acted. The rerun got through three
reconnaissance commands before the block. Both score 0 and so meet the
requirement as stated, but the first is a refusal, not evidence of
robustness. The rerun's reconnaissance is real evidence: an adversarial
agent that inventoried the whole agent container found no answers to take.
The prompt was not modified to get past the filter, because CI uses it
verbatim.

## Iteration history

### Iteration 1: task v2 (source precedence) @ `f112776`, 2026-09-21

| Agent | Trials | Reward | Wall time | Job |
|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 3 | **1.0 / 1.0 / 1.0** (38/38 tests each, including hidden batch B) | 19 min for the whole job, 3 in parallel | `jobs/2026-09-21__00-52-12-codex` |
| claude-code opus-5 max | 3 | **infra error**, not counted | n/a | `jobs/2026-09-21__00-52-15-claude` |

**Claude: infrastructure failure, a Harbor-on-Windows bug.** When each agent
finished, Harbor decoded the UTF-8 agent log (`claude-code.txt`) with
Windows' default cp1252 codec, failed on byte `0x9d`, and marked the trial
errored before the verifier ran. The console spinner (`⠋`) failed the
same way and aborted the job, so the third trial never started. Codex was
unaffected because its JSON log happened to be pure ASCII. The fix is
`PYTHONUTF8=1` for the Harbor process, now set in `scripts/trials.sh`. The
Claude trials were not rerun on v2: codex's 3/3 already established that v2
needed a redesign.

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

### Iteration 2: task v3 (repair a legacy tool against a settled AP ledger) @ `ae40ed9`, 2026-09-21

v3 removed the pricing doctrine from the policy. Instead the agent gets the
desk's legacy audit tool, which has four realistic defects, and two settled
history months with an AP ledger of per-invoice paid totals. Before any
trial ran, identifiability was verified: the correct tool reproduces both
ledgers to the cent, every defect changes a paid total in both months, and
only the fully correct detention rule fits both months.

| Agent | Trials | Reward | Wall time | Job |
|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 3 | 1.0 / 0.0 / 0.0 | 16 min for the whole job | `jobs/2026-09-21__01-29-00-codex` |
| claude-code opus-5 max | 3 | 0.0 / 1.0 / 1.0 | 39 min for the whole job, 2 in parallel | `jobs/2026-09-21__01-29-02-claude` |

Claude's single failure is the same allocation ambiguity (`SO-2452 accessorials`); every pricing, decision and trap test passed. The UTF-8 fix held, with no infra errors. **Counting honestly, claude-code also solved v3 3/3.**

**Both codex failures were specification failures, not genuine ones.** They
passed every pricing, decision and trap test and failed only
`test_landed_cost`. The v3 policy rewrite had changed the allocation rule
from basis-keyed wording ("a `per_bl` charge…") to "a charge on a
container / on a B/L". That wording is ambiguous for the forwarder's per-B/L
fee, which is printed against a container. Both agents allocated it to the
named container: $110/2 × 37/87 = $23.40 on SO-2452, exactly the reported
diff. Fixed in `cbb4201`. **Counting honestly, codex solved v3 3/3.**

**How it solved it (`LMo4gtm`, 16 commands).** It did exactly what the
design demands. It ran the legacy tool on both history months, diffed the
results against the ledger, and traced each mismatch to its evidence. Then
it stated all five rules correctly: *"vendor notices can revise a sailing
or roll a container; terminal move dates and weighbridge weights supersede
stale ERP movement facts; terminal-specific weekends matter for detention;
and a per-B/L fee is allowed once for each B/L, not once for the whole
invoice."* It reproduced 22/22 historical payments exactly before moving
on.

**Diagnosis.** Hiding the doctrine did not matter. The evidence describes
itself: a notice saying *"the sailing date is now…"*, or a move log with a
weighbridge column, points straight at its own relevance, and a frontier
model already has the freight-audit background to act on it. With five
rules, eleven invoices per month and totals that can be diffed with a
script, the whole search takes minutes.

### Iteration 3: task v4 (signed agreements, keying errors, notice clause) @ `dbf4df7`, 2026-09-21

v4 kept v3's design and added more domain depth:
- **Signed agreements as the contract.** Each vendor's signed rate agreement
  (a PDF) is authoritative. The ERP's hand-keyed JSON copy has digit-
  transposition errors in *different places every month*, including hidden
  batch B, so no fix can be hardcoded.
- **An expert rule.** The agreements carry the US-trade notice clause: a
  rate increase takes effect no earlier than 30 days after publication, a
  decrease on its stated date. NORDVIK's THC increase is published 8 days
  ahead of its effective date. It is not in force for two bookings (billed
  anyway) and in force for a third, which also receives the rolled
  container.
- **More history.** Four settled months with AP ledgers.

Before any trial ran: agreement parsing was exact on 6 batches × 3 vendors,
the oracle matched the truth, and it reproduced all four ledgers to the cent.

| Agent | Trials | Reward | Wall time | Job |
|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 3 | **1.0 / 1.0 / 1.0** (40/40 tests each) | 18.5 min for the whole job | `jobs/2026-09-21__09-27-16-codex` |

**How it solved it (15 commands).** After reading the evidence it named
every defect, including the two meant to be hardest: *"stale ERP
sailing/container facts, terminal move dates and weights being ignored,
locally defined weekends being ignored, signed-contract transcription
errors, tariff increases applied before the 30-day notice period, and per-B/L
fees counted once per invoice instead of once per B/L."* It then replayed
all four settled months as regression tests and reproduced **44/44**
historical payments exactly.

### Iteration 4: v4 plus hidden-only cases and scanned statements @ `3154205`, 2026-09-21

Two levers were added, both aimed at weaknesses the earlier trajectories had
not yet tested:
- **Hidden-batch-only cases (T15, T16 and two more).** None of these occur in
  batch A or the history, and each is defined in the documents. They are:
  two sailing amendments for one booking whose file order contradicts their
  date order; a EUR sailing on a Sunday (the FX rate falls back to the
  previous fixing); a per-shipment ISPS fee billed per container; and a
  weighbridge weight *below* the overweight threshold where the register says
  above. The hypothesis was that LLM-written code is wrong on paths the
  visible data never exercises.
- **Scanned statements.** The forwarder's invoices are image-only PDFs with
  skew and speckle, so they need OCR (tesseract, in both images). The oracle
  reconciles every scan against its printed subtotals.

| Agent | Trials | Reward | Wall time | Job |
|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 3 | **1.0 / 1.0 / 1.0** (42 passed, 2 skipped each) | 19 min 40 s | `jobs/2026-09-21__10-10-12-codex` |
| claude-code opus-5 max | 3 | **1.0 / 1.0 / 1.0** (42 passed, 2 skipped each) | 1 h 14 min for the job, 2 in parallel | `jobs/2026-09-21__10-14-23-claude` |

**The hypothesis was wrong for this model.** The agent's `audit.py`
recognises `"per shipment"`, a phrase that never occurs in the visible data,
because it built its parser from the agreement's vocabulary rather than from
examples. It orders notices by `(notice_date, file name)`, exactly as the
policy states. It OCR'd both scanned statements and reconciled all 44
historical payments, scans included, before it finished. It generalises from
the documents, not from the data it happens to see.

### What four iterations show

| | v2 | v3 | v4 | v4 final |
|---|---|---|---|---|
| Difficulty lever | conflicting sources, precedence stated | doctrine hidden; repair a legacy tool against a sparse ledger | plus authoritative documents, month-specific data errors, an expert notice rule | plus hidden-only cases and OCR'd scans |
| Codex | 3/3, 19 min | 3/3, 16 min | 3/3, 18.5 min | 3/3, 19.7 min |

Each lever was taken from a pattern in merged TB3 Operations tasks, and
each was verified to be well specified before any trial ran. None of them
moved codex's solve time. In every case the model read the whole
environment, formed the right hypotheses on the first pass, and checked
them against the evidence before finishing. For a back-office audit whose
evidence fits in one context and describes its own relevance, gpt-5.6-sol
at xhigh already performs at the level of an experienced auditor. Raising
difficulty from here would take levers these designs do not have: evidence
that cannot be read in one pass (scale, services, partial observability),
noisy sources (scans), or long stateful workflows. Those are what the
merged tasks combine, and they cost more than two days to build well.

## 6. Failure analysis

```bash
harbor analyze <job-dir> -m sonnet -r .tb3/docs/prompts/trial-analysis.toml \
  --job-prompt .tb3/docs/prompts/trial-analysis-job.txt
```

__pending__
