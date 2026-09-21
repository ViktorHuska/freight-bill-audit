# freight-bill-audit: a Terminal-Bench 3 task

Take-home for the Klavis AI Founding Engineer application: one original TB3
task. The agent acts as the freight auditor of an exporter's sales office.
It must build a reusable tool that audits a month of ocean-freight invoices
from two carriers (text PDFs) and a forwarder (scanned statements) and
allocates the approved cost to sales orders. The pricing doctrine is not
written down. The agent inherits the desk's flawed legacy tool and four
settled months of what accounts payable actually paid, and has to
reconstruct the facts from a stale ERP register, carrier notices, a terminal
move log and signed rate agreements. The verifier re-runs the tool on a
hidden batch.

| | |
|---|---|
| Task directory | [`tasks/freight-bill-audit/`](tasks/freight-bill-audit/): drop-in for the TB3 repo layout |
| Design and decisions | [`DESIGN.md`](DESIGN.md) |
| Checks, trials, cheat trials, iteration history | [`RESULTS.md`](RESULTS.md) |
| Data generator (dev only) | [`tools/generator/`](tools/generator/) |
| Reproduce checks / oracle / trials | [`scripts/`](scripts/) |

## Outcome

| Requirement (current TB3 CI) | Result |
|---|---|
| Static checks | ✅ 25 / 25 |
| Oracle / nop | ✅ 1.0 / 0.0 |
| Implementation rubric | see [RESULTS.md §2](RESULTS.md) |
| 3 × codex gpt-5.6-sol xhigh, all failing | ❌ **3 / 3 passed** (19.7 min) |
| 3 × claude-code opus-5 max, all failing | ❌ **3 / 3 passed** (74 min) |
| 1 × cheat per agent, reward 0 | ✅ 0 and 0. Claude made a full red-team attempt and found no bypass; the one lead it raised was tested with an exploit probe and hardened |

**The difficulty requirement was not met, and this repository documents
why.** Over two days the task went through four designs, each driven by the
previous trial evidence and each verified as well specified before any trial
ran:

1. **Conflicting sources.** The policy said which source wins.
2. **Repair a flawed legacy tool** against a sparse AP ledger.
3. **Signed agreements.** Month-specific ERP keying errors, and a 30-day
   notice rule for rate increases.
4. **Hidden-only edge cases** and OCR'd scanned statements.

Codex solved every version, 3/3 in 16–20 minutes. The trajectories show why
(RESULTS.md, *Iteration history*): the model reads the whole environment,
forms the right hypotheses on the first pass, and checks them against the
evidence before it finishes. For a back-office audit whose evidence fits in
one context, it already works at the level of an experienced auditor.

## Status

- [x] Generator: 6 batches (visible, hidden, 4 history), byte-deterministic
- [x] Oracle independent of the generator; agrees with truth and all ledgers
- [x] Static checks 25/25, oracle 1.0, nop 0.0
- [x] 3 × codex, 3 × claude-code standard trials (all passed; difficulty requirement not met)
- [x] 1 × codex, 1 × claude-code adversarial trials (reward 0)
- [x] Failure / iteration analysis
- [ ] Task README sections written by the author (TB3 requires human prose)
