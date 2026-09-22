# Results

Every command below was run from the repository root on Windows 11 with Docker
Desktop 28.4.0 (Linux containers, 20 CPUs / 31 GB), using the local `docker`
backend. Harbor 0.23.0, installed with `uv tool install harbor`. (TB3 CI pins `0.23.1.dev202609170426`; the one visible difference is that
0.23.0's `harbor analyze` lacks `--job-prompt`, so only the per-trial rubric ran.)

| | |
|---|---|
| Task version evaluated | **final: v5, commit `9e5503f`** (merged to `main` as `b3b9908`) for oracle, nop, all standard and all cheat trials in §3–§6. Earlier versions, including the v4 trials and cheat trials, are in *Iteration history*. |
| Artefacts in the repo | `jobs/` is git-ignored (full agent transcripts). `results/<job>/` keeps each final trial's grading evidence: `job_result.json`, and per trial `result.json`, `verifier/ctrf.json`, `verifier/reward.txt`, `verifier/batch_b_tool.log` (collected by `tools/collect_results.py`, which refuses any file matching a credential pattern). |
| Harbor redaction note | Harbor treats every `--ae` value as a secret and scrubs it from the files it saves. `trials.sh` passes `CLAUDE_FORCE_OAUTH=1` / `CODEX_FORCE_AUTH_JSON=1`, so every literal `1` in a saved job file reads `[REDACTED]`: `reward.txt` shows `[REDACTED]` for a reward of 1, `result.json` shows `[REDACTED].0`, and some `ctrf.json` files no longer parse as JSON. Grading happens before the scrub and is unaffected; the tables below read the test counts, which contain no `1`s here (46 / 0 / 2). |
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
harbor check tasks/freight-bill-audit -r .tb3/docs/prompts/task-implementation.toml   -m claude-opus-4-8 --ae CLAUDE_FORCE_OAUTH=1 --ae CLAUDE_CODE_OAUTH_TOKEN=<token>
```

**`harbor check` cannot run on native Windows for this rubric.** It passes the
whole reviewer instruction (the rubric plus the task) inline on a
`docker compose exec` command line. That exceeds Windows' 32,767-character
`CreateProcess` limit (`WinError 206`); Linux's ~2 MB limit is why CI never
hits it. The crash happens before any verdict is produced (jobs `C:/hc/rc`,
`jobs/rubric-check`).

This review was run on v4 (before v5). v5 kept the verifier hardening it
produced, and the v5 static checks, oracle and nop were re-run (§1, §3); the
rubric review itself was not repeated for v5.

**Substitute: an independent reviewer agent**, given the rubric
(`task-implementation.toml`) and the task files but not the author's
conclusions, graded every criterion. Summary:

| Outcome | Criteria |
|---|---|
| PASS (19) | verifiable, solvable, interesting, outcome_verified, anti_cheat_robustness, task_security, functional_verification, deterministic_reproducible, essential_difficulty, test_instruction_alignment (borderline), novel, agentic, solution_quality, separate_verifier_configured, environment_hygiene, structured_data_schema, typos, category_and_tags, task_name, resource_configuration, expert_time_estimate, ctrf_reporting, binary_reward |
| N/A (2) | artifact_efficiency, do_not_modify_enforced |
| FAIL, fixed | verifier_execution_isolation, no_extraneous_files, instruction accuracy ("two previous months": there are four), stale `solution/audit.py` docstring |
| FAIL, author | task_readme, difficulty/solution/verification_explanation_quality, reviewable: the four README sections must be written by the author |
| FAIL, acknowledged | **difficult**: the legacy tool shares the oracle's architecture, so the task reduces to finding its defects. The trials agree (§4). |
| disputed | task_toml_schema: `network_mode = "public"` comes verbatim from TB3's own `docs/task-template.toml`; `os` was removed |

**Fixes applied after the review:**
- `tests/test.sh`: `/logs/verifier` is made `chmod 700` before the agent's tool
  runs. The tool runs in its own session (`setsid`), and every `auditrun`
  process is killed (`pkill -KILL -u auditrun`) before grading. `procps` was
  added to the verifier image for `pkill`.
- `__pycache__` removed from the task and an `environment/.dockerignore`
  added (Docker ignores `.gitignore`, so local `.pyc` files were being copied
  into the image); the stray `tests/data/truth/.gitkeep` removed.
- `instruction.md`: "the two previous months" corrected to "four previous
  months".
- `solution/audit.py` docstring corrected; `os` removed from `task.toml`.

Re-verified after the fixes: static checks 25/25, oracle 1.0, nop 0.0
(`C:/hc/fo`, `C:/hc/fn`).

**Untested schema fields.** The reviewer noted that `invoice_total_usd`,
`currency`, `billed_amount_original` and literal two-decimal formatting are
not asserted. They were deliberately left unasserted after the trials:
adding assertions now would grade a different verifier from the one the
trials ran against.

## 3. Oracle and nop

```bash
harbor run -p tasks/freight-bill-audit --agent oracle --env docker --yes
harbor run -p tasks/freight-bill-audit --agent nop    --env docker --yes
```

| Agent | Reward | Tests | Runtime | Job |
|---|---|---|---|---|
| oracle | **1.000** | 46 passed, 2 skipped | 58 s | `jobs/v5-oracle` |
| nop | **0.000** | 46 failed | 36 s | `jobs/v5-nop` |

The oracle run covers the whole pipeline: `solve.sh` installs the reference
tool and makes batch A's 12 payment runs with it in the agent container. The
separate verifier then replays hidden batch B's 12 runs through that same
tool as the unprivileged `auditrun` user, staging before each run only the
inbox folders that have arrived by its date (all 12 exit 0), and grades both
batches.

### Independent cross-check of ground truth

Ground truth is computed twice, by code that shares nothing: the generator
(`tools/generator/`, at planting time) and the reference solution
(`solution/audit.py`, from `policy.md` alone). `tools/replay_check.py` replays
a batch through the oracle exactly as the verifier stages it and diffs every
run:

| Batch | Runs | Invoices | Lines | Adjustments | Result |
|---|---|---|---|---|---|
| A | 12 | 11 | 85 (27 disputed) | 2 | identical at every run: postings, held invoices; then every status, match, line amount, decision, reason, paid-to-date and landed-cost cell |
| B | 12 | 11 | 91 (32 disputed) | 3 (one a recovery claim) | identical |
| h1–h4 | 11–12 each | 11 each | 85 each | 2 each | all 52 ledger postings reproduced exactly |

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
| codex gpt-5.6-sol xhigh | 1 (`gQtLJpX`) | 1.0 | job 30 min 9 s (3 in parallel) | genuine pass | none: 46 passed, 2 skipped |
| codex gpt-5.6-sol xhigh | 2 (`isUubAf`) | 1.0 | 〃 | genuine pass | none: 46 passed, 2 skipped |
| codex gpt-5.6-sol xhigh | 3 (`jkeDAoz`) | 1.0 | 〃 | genuine pass | none: 46 passed, 2 skipped |
| claude-code opus-5 max | 1 (`ZcucctJ`) | 1.0 | job 1 h 48 min (2 in parallel, then the third) | genuine pass | none: 46 passed, 2 skipped |
| claude-code opus-5 max | 2 (`LFTBxRS`) | 1.0 | 〃 | genuine pass | none: 46 passed, 2 skipped |
| claude-code opus-5 max | 3 (`f99B9vB`) | 1.0 | 〃 | genuine pass | none: 46 passed, 2 skipped |

Jobs: `jobs/2026-09-21__17-29-18-codex`, `jobs/2026-09-21__18-50-57-claude`.
The 2 skipped tests are the per-trap tests for T15/T16 on batch A, which
plants neither (both are hidden-batch-only by design).

Every pass is genuine: each agent's own `audit.py` was replayed unchanged
through hidden batch B's 12 payment runs in the verifier, seeing only what
had arrived by each run (every run exited 0), and matched the truth at every
run and on every field afterwards. The truth never exists in the agent
container.

**How they solved it.** All six trials worked the same way. Each built the
stateful tool, then replayed the four settled months through it and
reproduced **all 52 historical postings** exactly (run date, invoice, kind,
cent) before finishing. Each then named every legacy defect in its final
report, including the v5 ones: the +37.00 adjustment caused by the late roll
advice, the detention hold, and the 30-day notice clause.

**The TB3 requirement that every standard trial fails is not met.**

**Trials rerun because of infrastructure failures.** The first claude-code
job on v5 (`jobs/2026-09-21__18-33-16-claude`) lost all three trials before the
agent started: `AgentSetupTimeoutError` after Harbor's 360 s agent-install
limit. At the time, the claude-code binary was downloading at about 0.8 MB/s
(measured from a container: 32.5 MB in 40.6 s). The rerun above used
`SETUP_TIMEOUT_MULT=3` (`--agent-setup-timeout-multiplier 3`), which raises
only the install limit; the agent's 28 800 s task timeout is unchanged. In
iteration 1, the claude-code job was lost to a Harbor-on-Windows UTF-8 bug
(see *Iteration history*); it was fixed before any later run.

## 5. Adversarial trials (`/cheat`)

```bash
CHEAT=1 bash scripts/trials.sh codex
CHEAT=1 bash scripts/trials.sh claude
```

As in `run-cheat-trials.yml`, `docs/prompts/hack-trial-prompt.md` is
**appended** to the instruction in a throwaway copy of the task, and one trial
runs per agent.

**On the final task (v5):**

| Agent | Reward | What the agent attempted | Why it scored 0 |
|---|---|---|---|
| codex (`jobs/2026-09-21__18-44-51-codex-cheat`) | **0** | nothing: its first turn was blocked by OpenAI's platform ("flagged for possible cybersecurity risk") | no deliverable |
| claude-code (`jobs/2026-09-21__18-52-06-claude-cheat`) | **0** | a full red-team pass. It tried reading the history ledgers at run time (the graded batches ship without one), wrapping the legacy tool (it diverges from the ledger, e.g. NOR-H1-0104 5087 vs 4807, and skips the scans), placeholder outputs, tampering with the `/logs` host mounts (write-only sinks, nothing to forge), hardcoding the month (the hidden month differs; the scans need OCR), and pre-seeding the state directory (the verifier's runs start with fresh state) | no bypass found. It reported "the only path that passes verification is the intended legitimate solution" and left no deliverable |

Infrastructure reruns: the first attempt of each (`jobs/2026-09-21__18-31-24-codex-cheat`,
`jobs/2026-09-21__18-38-13-claude-cheat`) died in agent setup
(`AgentSetupTimeoutError`, see §4) before the agent ran.

**On v4 (kept for the record; the verifier hardening below came from these):**

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

### Iteration 5: v5, the month as it happens (payment runs) @ `9e5503f`, 2026-09-21

The earlier analysis pointed at one lever none of the designs had yet used:
evidence that cannot be taken in one pass. v5 applies the pattern of the
merged `freight-dispatch-shift` task (a cutoff-scoped event feed with
irreversible commits):
- **Partial observability.** Invoices, notices and terminal move-log exports
  arrive in dated inbox folders. AP pays at 11 to 12 runs a month (Fridays and
  month-end). The tool makes one run per call and keeps its own state; the
  verifier stages batch B's inbox run by run, so the future does not exist
  when a run is made.
- **Irreversible postings.** Detention invoices are held until the terminal
  reports the empty return. Payments are final: late evidence (a weighbridge
  row after an overweight line was short-paid on the register weight, a roll
  advice the day after the receiving booking's invoice was paid) must be
  settled by an ADJUSTMENT: a supplementary payment or, in hidden batch B
  only, a recovery claim.
- **Allocation fixed at posting time.** Each posting is allocated on the
  facts on file when it is made and never re-allocated. A month-end
  recomputation with full knowledge gives a different landed cost.

Rejected on the way: making every invoice a degraded scan. A calibration
sweep with the task's own tesseract showed a cliff, not a slope. Up to
moderate blur and JPEG noise, naive OCR misread **0 of 173** key fields; at
heavy degradation it misread 8%, and no preprocessing recovered them. At that
point the information is destroyed rather than hard to read, so the
difficulty would have come from noise, not skill.

Before any trial: the oracle matched the truth at every one of the 12 runs of
A and B, and reproduced all 52 history postings exactly (`tools/replay_check.py`).
Oracle 1.0 (46 passed), nop 0.0, static checks 25/25.

| Agent | Trials | Reward | Wall time | Job |
|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 3 | **1.0 / 1.0 / 1.0** | 30 min 9 s for the whole job | `jobs/2026-09-21__17-29-18-codex` |
| claude-code opus-5 max | 3 | **1.0 / 1.0 / 1.0** | 1 h 48 min for the job, 2 in parallel | `jobs/2026-09-21__18-50-57-claude` |

**How they solved it.** The same way as before, with more work: each agent
built the stateful tool, then replayed all four settled months through it and
reproduced **52/52 historical postings** before finishing. One codex trial
also re-ran its runs to prove they were idempotent. The history ledger, which
is what makes the undocumented pricing rules fair to discover, is also a
complete regression test for the new run-by-run rules. v5 moved codex's solve
time from about 20 minutes to 30, and claude-code's from 74 minutes to under
two hours, and nothing else.

### What five iterations show

| | v2 | v3 | v4 | v4 final | v5 (final) |
|---|---|---|---|---|---|
| Difficulty lever | conflicting sources, precedence stated | doctrine hidden; repair a legacy tool against a sparse ledger | plus authoritative documents, month-specific data errors, an expert notice rule | plus hidden-only cases and OCR'd scans | plus partial observability: payment runs, holds, irreversible postings, allocation fixed at posting time |
| Codex | 3/3, 19 min | 3/3, 16 min | 3/3, 18.5 min | 3/3, 19.7 min | 3/3, 30 min |
| Claude-code | (infra loss) | 3/3, 39 min | — | 3/3, 74 min | 3/3, 1 h 48 min |

Each lever was taken from a pattern in merged TB3 Operations tasks, and
each was verified to be well specified before any trial ran. None of them
produced a single failed test. In every case the model read the whole
environment, formed the right hypotheses on the first pass, and checked
them against the evidence before finishing.

The deciding factor is the one element every version shares: the settled
history. It is what makes rules that are not written down fair to discover,
and for the same reason it is a complete regression suite. Both agents use
it exactly as an auditor would, reproducing every historical payment before
they trust their tool. Partial observability (v5), the lever the earlier
analysis predicted would work, did not change that: once the history showed
the run-by-run consequences, the agents implemented them and verified them
posting by posting. Scan noise was measured and rejected (above). What is
left to add, more rules and more months, makes the task longer, not harder.

## 6. Failure analysis

```bash
harbor analyze jobs/<job> -m sonnet -n 3 -r .tb3/docs/prompts/trial-analysis.toml   --ae CLAUDE_FORCE_OAUTH=1 --ae CLAUDE_CODE_OAUTH_TOKEN=<token>
```

This runs TB3's per-trial analysis rubric over every final job (jobs
`analyze-*`). CI also passes `--job-prompt` for a job-level summary; Harbor
0.23.0 does not have that flag, so only the per-trial checks ran.

| Trials | task_specification | reward_hacking | difficulty_crux | near_miss | refusals | low_timeout |
|---|---|---|---|---|---|---|
| codex ×3 (standard) | pass ×3 | pass ×3 | pass ×3 | pass ×3 | pass ×3 | pass ×3 |
| claude-code ×3 (standard) | pass ×3 | pass ×3 | pass ×3 | pass ×3 | pass ×3 | pass ×3 |
| codex cheat #1 | n/a | pass | n/a | pass | **fail** (platform block) | n/a |
| codex cheat #2 | n/a | **fail** (attempted; found nothing) | n/a | pass | **fail** (platform block) | n/a |
| claude-code cheat | pass | pass | pass | pass | pass | pass |

**Reading it.**
- `task_specification` passes on all six standard trials. The analyzer found
  no gap between the instruction, the documents and the tests, so the
  agents had what they needed and used it. The task is well specified. What
  it lacks is difficulty.
- There are no failures to attribute to a trap. No standard trial failed a
  single test, so the per-trap breakdown is empty for the final version. The
  only failures in the whole project were the two iteration-2 allocation
  failures, which were a **specification** failure (see *Iteration
  history*), found and fixed.
- The codex cheat verdicts are what the adversarial prompt is designed to
  produce: the rerun *attempted* to find something to tamper with (hence
  `reward_hacking: fail`), found nothing, and scored 0. The `refusals` flags
  record OpenAI's platform block, not a choice by the task.
- The claude-code cheat trial is the substantive adversarial result. It
  engaged fully, found no bypass, left no deliverable and reported that
  honestly. Its one lead was tested and hardened (§5).

**Where difficulty would have to come from.** Across five designs, codex
solved every version in 16–30 minutes and claude-code in 40 minutes to under
two hours. The last design added the lever this analysis previously
predicted would work (partial observability with irreversible state), and
it did not. In this domain, what makes a task fair (a settled history from
which undocumented rules can be learned) is also what makes it solvable: it
gives the agent a complete regression suite. A task that defeats these
agents would have to withhold that feedback loop without becoming
unspecified, for example grading judgements that no history can confirm, or
evidence that is expensive to gather and cannot all be gathered.
