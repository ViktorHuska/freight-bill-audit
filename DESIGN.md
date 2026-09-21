# Design: `freight-bill-audit`

The decisions behind the task, for the repository reader and the interview.
Nothing here ships into the task directory.

## 1. What the agent delivers

| Artifact | Purpose |
|---|---|
| `/app/audit.py` | A single-file CLI that audits a batch of freight invoices against the register, the controlling sources and the house policy. |
| `/app/output/audit.json` | The tool's result for the visible batch. |
| `/app/output/landed_cost.csv` | Approved cost allocated to each sales order for the visible batch. |

**The deliverable is a tool, not answers.** The verifier re-runs `audit.py`,
unchanged, on a hidden second batch: same vendors, layouts and contract
families, but a different period, ids, rates and index rows. A hand-written
`audit.json` for the visible batch scores zero, because every batch B test
fails.

## 2. Where the difficulty lives: source precedence

The first draft put every rule in `policy.md`, including the answer to each
trap ("sailing date, **not** invoice date"). That made it a careful-reading
exercise, which frontier models are good at, and the difficulty that remained
was clerical. The merged TB3 Operations tasks (`heat-pump-warranty`,
`intrastat-meldung`) point to a better source of difficulty: **the agent must
reconstruct the facts from sources that disagree** before any rule can be
applied.

So the ERP register is stale on purpose, and `policy.md` §2 says which source
controls each fact:

| Fact | Controlling source | Stale source |
|---|---|---|
| Sailing date | carrier sailing-amendment notice | `shipments.json` |
| Container → booking | carrier roll advice | `shipments.json` |
| Gate-out / empty-return | `terminal_moves.csv` | `shipments.json` (planned dates) |
| Gross weight | `terminal_moves.csv` weighbridge | `shipments.json` |
| Rates | tariff circular in force on the sailing date | `contracts/*.json` |

The policy states the precedence but does not list the discrepancies; finding
them is the agent's job.

**Why it is hard rather than long: a single wrong fact cascades.** A sailing
amendment across a version boundary changes the contract version, the BAF
month and the EUR fixing date together. Several lines change amount and
decision, the invoice's status changes, and the landed cost of every sales
order in those containers moves. A tool that reads only the register produces
a plausible, internally consistent and wrong result.

**One genuine domain fact.** Terminals have their own weekends:
Jeddah (`SAJED-KCT`) runs Friday/Saturday, Karachi Sunday only.
`holidays.json` states this for each terminal, but a tool that hardcodes
Mon–Fri miscounts detention days.

## 3. Trap registry

Each batch plants all 13. The generator refuses to write a batch unless every
trap lands with exactly the decision and reason below (`generate.py`,
`EXPECTED`).

| id | Trap | Outcome | What a careless tool does |
|---|---|---|---|
| T01 | Sailing amendment crosses a contract-version and month boundary | DISPUTE / RATE_MISMATCH | reads the register date: old version, old BAF row; misses the over-billing |
| T02 | Circular raises THC_O; vendor bills the stale amount | APPROVE / UNDERBILLED | ignores the circular: says OK, wrong expected |
| T03 | Circular lowers BAF; vendor bills the stale row | DISPUTE / RATE_MISMATCH | ignores the circular: approves an over-charge |
| T04 | Detention on register dates in calendar mode at a Fri/Sat working-day terminal | DISPUTE / FREE_TIME_MISCOUNT | wrong dates, or Mon–Fri weekend: wrong day count |
| T05 | Per-B/L fee billed per container on a two-carrier forwarder consolidation | DISPUTE / BASIS_ERROR | pays every line, or applies one fee for the whole invoice |
| T06 | Container rolled to another booking after the export | APPROVE / OK, matched to the new booking | matches the register booking; allocation shifts |
| T07 | Overweight justified by the weighbridge, not the register weight | APPROVE / OK | disputes a legitimate charge |
| T08 | Ocean freight at the contract minimum | APPROVE / OK | disputes a legitimate charge |
| T09 | Charge code absent from the contract | DISPUTE / UNAUTHORIZED_CHARGE | prices it |
| T10 | Duplicate re-issued under a new number and date | DISPUTE / DUPLICATE_INVOICE | pays twice |
| T11 | Credit note against an over-billed line | APPROVE / CREDIT_NOTE | ignores it or disputes it |
| T12 | Invoice for a shipment never booked | DISPUTE / UNMATCHED | invents a match |
| T13 | EUR converted at the sailing-date fixing | APPROVE / OK | uses the invoice date |

Two traps (T07, T08) are legitimate charges that look wrong, so disputing
everything unusual fails as well.

## 4. Ground truth: two independent computations

```
tools/generator/          dev tooling, not in the task dir
  policy.md               canonical rulebook, copied verbatim into both batches
  models.py               register (reg_*) vs controlling (act_*) fields
  world.py                explicit world per batch: bookings, contracts, circulars, notices
  invoices.py             bills each invoice the way the vendor would, errors included
  pricing.py              the generator's reading of policy §3, from controlling facts
  truth.py                decisions, status, matching, largest-remainder allocation
  render.py               three text-PDF vendor layouts (reportlab, invariant mode)
  io_utils.py             writes the files the agent receives
  generate.py             orchestrator plus self-check invariants
```

* `invoices.py` never decides an outcome; `truth.py` recomputes every expected
  amount, decision and reason from the policy.
* `solution/audit.py` is a third reading, written from `policy.md` alone and
  sharing no code with the generator. On both batches it agrees with the truth
  on every field (see RESULTS.md §3). A disagreement would have meant an
  ambiguous policy or a bug on one side.
* Writing the generator and oracle surfaced two ambiguities in the policy,
  which were fixed before any agent saw it: how a per-B/L fee is assigned on a
  multi-B/L invoice, and how a detention variance is classified.
* The world is written out explicitly rather than sampled, so every trap
  precondition holds by construction and a batch regenerates byte for byte
  (LF line endings, reportlab `invariant=1`).

## 5. Verifier

* `tests/Dockerfile` bakes Python 3.13, pdfplumber, pypdf, pandas,
  python-dateutil, `pytest==9.1.1`, `pytest-json-ctrf==0.5.2`, batch B inputs
  and both truth files. Nothing is fetched at verify time.
* `tests/test.sh`: makes the truth root-only (`chmod 700`), runs the agent's
  tool on batch B as the unprivileged `auditrun` user under `timeout`, then
  runs pytest as root. The tool's output is only ever parsed as data.
* **No agent `requirements.txt`.** An earlier design installed the agent's
  pinned requirements as root before pytest ran as root, so a package with a
  `pytest11` entry point would have been auto-loaded into the grader. The
  oracle needs only the preinstalled packages, so the manifest was dropped.
* Tests are grouped per trap with a one-line description each, so
  `harbor analyze` can attribute a failure to the rule that was missed.
* Money is compared exactly at cents. That is fair because the policy fixes
  the rounding point (§3.10) and the largest-remainder tie-break (§7.4); a
  correct implementation has no freedom to differ.
* Reward is binary.

## 6. Rubric fit

* **Verifiable / deterministic:** fixed data, exact comparison, no network, no LLM judge.
* **Solvable:** the oracle is about 430 lines; an expert who knows the rules writes it in 3–4 hours.
* **Difficult for a good reason:** the difficulty is reconstructing facts from conflicting evidence, and it cascades. An experienced freight auditor checks the carrier's amendments and the terminal's own records by habit; a junior AP clerk trusts the ERP.
* **Outcome-verified / agentic:** the agent must explore PDFs, a register, a move log, correspondence and contracts, and build a tool that generalises. Only outputs are graded.
* **Anti-cheat:** hidden batch, truth unreadable by the tool, no manifest install, no answers anywhere in `/app`.
* **Novel:** the closest merged task, `freight-dispatch-shift`, plans dispatch. None audits transport invoices or allocates landed cost.

## 7. Resources

* 2 CPUs / 4096 MB: pdfplumber on 11 small PDFs is light.
* Agent timeout 28800 s, matching every merged Operations task (TB3 raised
  them all to 8 h in PR #1800).
* Verifier timeout 900 s. The tool on batch B plus pytest takes well under a
  minute; the margin is for slow agent implementations.
