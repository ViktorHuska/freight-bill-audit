# Design: `freight-bill-audit`

This document records the architectural decisions behind the task. It is for the
repository reader (and for the interview), not for the agent. Nothing here ships
into the task directory.

## 1. What the agent must deliver

| Artifact | Purpose |
|---|---|
| `/app/audit.py` | A single-file CLI that audits a batch of freight invoices against contracts, shipment data and the house policy. |
| `/app/output/audit.json` | The tool's result for the visible batch in `/app/data`. |
| `/app/output/landed_cost.csv` | Landed cost per sales order for the visible batch. |
| `/app/requirements.txt` | Pinned extra Python deps (may be empty). |

**Decision: the deliverable is a tool, not just answers.** The verifier re-runs
`audit.py` on a second, hidden batch (same vendors, same contract families,
different invoices/shipments/traps). This is the anti-cheat backbone: a hardcoded
`audit.json` for the visible batch scores zero, because the hidden-batch tests fail.
It also matches the TB3 preference for outcome verification — we grade what the
tool produces, never how it parses PDFs.

## 2. Where the complexity lives

The instruction stays short (2–3 paragraphs). All business rules live in the
environment as documents an auditor would actually have:

```
/app/data/
  policy.md              house audit SOP: matching, decisions, tolerances, allocation, rounding, FX
  shipments.json         bookings -> containers -> sales-order lines (weights, cbm, values, gate dates)
  contracts/<VENDOR>.json rate contracts with validity windows, lane rates, surcharge index tables,
                         accessorial basis (per container / per B/L), detention tiers, minimums
  holidays.json          terminal holiday calendars (used by free-time counting)
  fx.csv                 daily EUR/USD fixings
  invoices/*.pdf         ~36 text-based PDFs across 4 vendor layouts
```

The rules are individually simple; the difficulty is that they are *coupled*.
Every trap fires against a rule that a naive implementation gets wrong in a way
that looks plausible, and one wrong decision moves downstream numbers (approved
amount -> allocation -> landed cost -> cent reconciliation).

## 3. Trap registry (the difficulty budget)

Each trap is a function that takes a clean invoice, mutates it, and records the
expected decision. Batch A and Batch B are drawn from the same registry with
different seeds and every trap fires at least once in both.

| id | Trap | Why agents get it wrong |
|---|---|---|
| T01 | BAF/fuel index keyed to **sailing month**, invoice dated the next month | uses invoice date |
| T02 | Contract version boundary — booking sailed under v2 rates, invoice references v1 | picks latest version or invoice date |
| T03 | Detention free time counted in **working days** at one terminal, calendar days at others, with holiday calendar | ignores terminal rule or holidays |
| T04 | Per-B/L fee (doc fee) billed once **per container** | multiplies by containers |
| T05 | Minimum charge floor — billed amount exceeds computed lane rate because minimum applies; **legitimate** | disputes a correct invoice |
| T06 | Duplicate invoice re-issued with new invoice number and date | pays twice |
| T07 | Credit note netting against an earlier invoice | treats as a charge or ignores |
| T08 | EUR invoice converted at policy's FX date rule (sailing date, not invoice date) | uses invoice date |
| T09 | Booking number typo on invoice; containers still match | leaves invoice unmatched |
| T10 | Split shipment: one sales order across two B/Ls | allocates the whole SO to one B/L |
| T11 | Accessorial not in contract -> `UNAUTHORIZED_CHARGE` (expected = 0, dispute) | tries to price it |
| T12 | Overweight band triggered because packing-list weight > booked weight; **legitimate** surcharge | uses booked weight, disputes |
| T13 | Variance inside policy tolerance -> `WITHIN_TOLERANCE`, approve at billed amount | disputes tiny variances |
| T14 | Forwarder invoice consolidating charges for two B/Ls, one of them belonging to a different vendor's contract | prices both with one contract |

Calibration rule: if an agent trial passes, deepen a coupling (e.g. make T03 and
T08 interact), never add invoices.

## 4. Ground truth — two independent computations

```
tools/generator/          (dev tooling, NOT in the task dir)
  models.py               dataclasses for world, invoices, truth
  world.py                builds bookings/containers/SOs/contracts deterministically from a seed
  traps.py                registry; each trap plants a mutation AND writes its expected outcome
  render.py               vendor PDF layouts (reportlab), text-based
  generate.py             orchestrator: world -> clean invoices -> traps -> PDFs -> truth
```

* The **generator** plants each trap with an explicit expected outcome computed at
  planting time from the intended rule.
* The **solution** (`solution/audit.py`) is an independent implementation that
  computes outcomes from the documents alone.
* The oracle run is therefore a cross-check of two implementations. If they
  disagree, either the policy text is ambiguous or one implementation is wrong —
  both are bugs to fix before any agent sees the task.

Generated data is committed; the generator is run by the author, never by CI or
the agent.

## 5. Verifier design

* `tests/Dockerfile` bakes: Python 3.13, `pdfplumber` + `pypdf` (pinned), pandas
  (pinned), `pytest==9.1.1`, `pytest-json-ctrf==0.5.2`, batch B inputs and both
  truth files. Nothing is fetched at trial time.
* `tests/test.sh`:
  1. optionally installs the agent's pinned `requirements.txt` (allowed by the
     implementation rubric for separate verifiers)
  2. locks `/tests/data/truth` to root only (`chmod 700`)
  3. runs the agent's `audit.py` on batch B **as an unprivileged user**, so the
     tool cannot read truth files even though it executes in the verifier container
  4. runs pytest as root
* Tests are grouped per trap with descriptive docstrings so `harbor analyze` can
  attribute failures to specific rules.
* Money is compared exactly (cents). No tolerances beyond those the policy itself
  states.
* Reward is binary: all tests pass or reward 0.

## 6. Why this satisfies the rubric

* **verifiable / deterministic** — fixed data, exact comparison, no network, no LLM judge.
* **solvable** — the oracle is ~400 lines of Python an expert writes in 2–4 h once the rules are understood.
* **difficult for a good reason** — every trap is a real freight-audit failure mode; a junior AP clerk gets them wrong, an experienced freight auditor does not.
* **outcome-verified / agentic** — the agent must read PDFs, four data files and a policy, decide, and build a reusable tool; only outputs are graded.
* **anti-cheat** — hidden batch, truth unreadable by the tool, no answers anywhere in `/app`.
* **novel** — no merged task audits transport invoices or allocates landed cost.

## 7. Resource decisions

* 2 CPUs / 4096 MB — pdfplumber on ~36 small PDFs is light; headroom for agents that install pandas.
* Agent timeout 28800 s (8 h cap enforced by `check-task-timeout.sh`).
* Verifier timeout 900 s — running the tool on batch B plus pytest is well under a minute; margin for slow tool implementations.
