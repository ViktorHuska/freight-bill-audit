# freight-bill-audit: a Terminal-Bench 3 task

Take-home for the Klavis AI Founding Engineer application: one original TB3
task. The agent acts as the freight auditor of an exporter's sales office.
It must build a reusable, stateful tool that audits a month of ocean-freight
invoices from two carriers (text PDFs) and a forwarder (scanned statements)
**as the month happens**: documents arrive day by day, accounts payable pays
at weekly payment runs, and each run may use only what has arrived by then.
Late evidence has to be settled by adjustments, because payments are final.
What is paid is allocated to sales orders. The pricing doctrine is not
written down: the agent inherits the desk's flawed legacy tool and four
settled months of what AP actually posted, and has to reconstruct the facts
from a stale ERP register, carrier notices, a terminal move log and signed
rate agreements. The verifier replays a hidden month through the tool, run
by run.

| | |
|---|---|
| Task directory | [`tasks/freight-bill-audit/`](tasks/freight-bill-audit/): drop-in for the TB3 repo layout |
| Design and decisions | [`DESIGN.md`](DESIGN.md) |
| Checks, trials, cheat trials, iteration history | [`RESULTS.md`](RESULTS.md) |
| Data generator (dev only) | [`tools/generator/`](tools/generator/) |
| Reproduce checks / oracle / trials | [`scripts/`](scripts/) |
| Grading evidence of the final trials | [`results/`](results/) |

## Outcome

| Requirement (current TB3 CI) | Result |
|---|---|
| Static checks | ✅ 25 / 25 |
| Oracle / nop | ✅ 1.0 / 0.0 |
| Implementation rubric | see [RESULTS.md §2](RESULTS.md) (`harbor check` cannot run on Windows; independent review substituted) |
| 3 × codex gpt-5.6-sol xhigh, all failing | ❌ **3 / 3 passed** (30 min) |
| 3 × claude-code opus-5 max, all failing | ❌ **3 / 3 passed** (1 h 48 min) |
| 1 × cheat per agent, reward 0 | ✅ 0 and 0. Claude made a full red-team attempt and found no bypass; codex was blocked by OpenAI's platform filter |

**Unfortunately, the difficulty requirement was not met, and this repository documents
why.** Over three days the task went through five designs, each driven by the
previous trial evidence and each verified as well specified before any trial
ran:

1. **Conflicting sources.** The policy said which source wins.
2. **Repair a flawed legacy tool** against a sparse AP ledger.
3. **Signed agreements.** Month-specific ERP keying errors, and a 30-day
   notice rule for rate increases.
4. **Hidden-only edge cases** and OCR'd scanned statements.
5. **Partial observability and irreversible state** (the final version):
   payment runs, held invoices, adjustments, allocation fixed at posting time.

Both agents solved every version without failing a single test. The
trajectories show why (RESULTS.md, *Iteration history*): the settled
history, which is what makes undocumented rules fair to discover, is also a
complete regression suite, and both agents reproduce every historical
posting before they trust their tool.

## Status

- [x] Generator: 6 batches (visible, hidden, 4 history), byte-deterministic, run-by-run truth
- [x] Oracle independent of the generator; agrees with truth at every run and with all ledgers
- [x] Static checks 25/25, oracle 1.0, nop 0.0
- [x] 3 × codex, 3 × claude-code standard trials (all passed; difficulty requirement not met)
- [x] 1 × codex, 1 × claude-code adversarial trials (reward 0)
- [x] Failure / iteration analysis; grading evidence in [`results/`](results/)
