# Design: `freight-bill-audit`

The decisions behind the task, for the repository reader and the interview.
Nothing here ships into the task directory. The iteration history, with the
trial evidence that drove each change, is in [RESULTS.md](RESULTS.md).

## 1. The job

A freight auditor at an exporter's international sales office checks every
ocean-freight invoice (from two carriers and a forwarder) before accounts
payable pays it, and allocates what is paid to sales orders. The month is
audited as it happens: documents arrive day by day, AP pays at weekly payment
runs, and a run can only use what has arrived by then. The agent does that
job by building a reusable, stateful tool:

| Artifact | Purpose |
|---|---|
| `/app/audit.py` | Single-file CLI that makes one payment run, keeping state between runs |
| `/app/output/runs/<date>.json` | Each run's postings (PAYMENT / ADJUSTMENT) and held invoices |
| `/app/output/audit.json` | After the last run: per-invoice status, paid to date, and per-line billed / expected / variance / decision / reason |
| `/app/output/landed_cost.csv` | Paid cost per sales order, by category, summed over all postings |

**The deliverable is a tool, not answers.** The verifier replays hidden
batch B through `audit.py`, unchanged, one payment run at a time, staging
before each run only the inbox folders that have arrived by its date. A
hand-written answer for the visible batch scores zero.

## 2. What the agent is given

```
/app/data/              this month's batch
  payment_runs.txt        the month's run dates (every Friday and month-end)
  inbox/YYYY-MM-DD/       what arrived that day:
    invoices/*.pdf          text PDFs (two carriers) and SCANNED statements (forwarder)
    notices/*.txt           sailing amendments, container rolls, tariff circulars
    terminal_moves.csv      the terminals' full move log as of that day
  shipments.json          ERP booking register export (stale on purpose)
  contracts/<V>_agreement.pdf   signed rate agreement (authoritative)
  contracts/<V>.json            the ERP's hand-keyed copy (has keying errors)
  holidays.json, fx.csv   terminal weekends + closures, EUR/USD fixings
  policy.md               decision table, duplicates, allocation, payment runs, schema
/app/legacy/audit_legacy.py   the desk's current tool (month-end, whole inbox at once)
/app/history/h1..h4/          four settled months, each with ap_ledger.csv (every posting, by run)
```

`policy.md` deliberately does **not** state the pricing doctrine. Instead it
says the legacy tool implements how the desk prices charges, that the tool
is not always right, and that what AP actually paid, recorded in the
history ledgers after the senior auditor's review, is authoritative.

## 3. Where the difficulty is meant to be

Four layers, each taken from a pattern in merged TB3 Operations tasks:

1. **Reconstructing the facts from conflicting sources.** The register is
   stale. The controlling facts are in carrier notices (sailing amendments,
   container rolls), the terminal move log (gate dates, weighbridge
   weights) and the signed agreements. One wrong fact cascades: a sailing
   amendment moves the contract version, the surcharge month and the FX date
   together.
2. **Repairing a flawed system against sparse evidence.** The legacy tool
   has these defects:
   - it ignores amendments and rolls
   - it uses register dates and a Mon–Fri weekend for detention
   - it uses register weights
   - it treats per-B/L fees as once per invoice
   - it prices from the ERP copy of the contracts
   - it applies rate increases before their notice period
   - it skips the scanned statements

   The only feedback is what AP posted per invoice at each run of four
   settled months, as totals. The
   ERP keying errors differ every month, so nothing can be hardcoded.
3. **Domain rules that only a careful expert applies.**
   - Terminals keep their own weekends (Jeddah's is Friday/Saturday).
   - The US-trade notice clause: a rate increase takes effect no earlier
     than 30 days after publication, a decrease immediately. A THC increase
     published 8 days ahead applies to one booking and not to two others.
   - A per-B/L fee on a two-carrier forwarder consolidation is due once per
     B/L, not once per invoice.

4. **Partial observability and irreversible state (v5).** The pattern of
   the merged `freight-dispatch-shift` task. Evidence arrives during the
   month, and each payment run may use only what is on file by its date:
   - A detention invoice is **held** until the terminal reports the empty
     return; register dates are plans, not evidence.
   - Payments are final. When late evidence changes an approved amount
     (a weighbridge row landing after an overweight line was short-paid on
     the register weight, or a roll advice arriving the day after the
     receiving booking's invoice was paid), the run posts an **ADJUSTMENT**:
     a supplementary payment or a recovery claim.
   - Each posting is **allocated on the facts on file when it is made** and
     never re-allocated, so a per-B/L fee paid before a roll was known stays
     split over the containers the B/L had then. Recomputing everything at
     month end with full knowledge gives a different landed cost.
   - The terminals re-send the whole move log; only the latest copy on file
     counts.

The hidden batch adds four cases that never occur in the visible data or
the history, each defined by the documents: superseding notices whose file
order contradicts their dates, a Sunday EUR sailing (FX falls back to the
Friday fixing), a per-shipment fee, and a weighbridge weight *below* the
overweight threshold. The last one is also the only **negative** adjustment:
the register-weight overweight charge is paid, then recovered when the
weighbridge row arrives. The forwarder's statements are scans, so reading
them needs OCR.

## 4. Traps (16)

| id | Trap | Batches |
|---|---|---|
| T01 | sailing amendment moves contract version, BAF month and FX date | all |
| T02 | rate increase billed before its 30-day notice period | all |
| T03 | tariff circular lowers BAF; vendor bills the stale row | all |
| T04 | detention: move-log dates, terminal's own working days | all |
| T05 | per-B/L fee billed per container on a consolidation | all |
| T06 | container rolled to another booking after the export | all |
| T07 | overweight justified by weighbridge weight (legitimate) | all |
| T08 | ocean freight at the contract minimum (legitimate) | all |
| T09 | charge code not in the agreement | all |
| T10 | duplicate re-issued under a new number | all |
| T11 | credit note against an over-billed line | all |
| T12 | invoice for a shipment never booked | all |
| T13 | EUR at the sailing-date fixing | all |
| T14 | rate increase correctly in force after its notice period (legitimate) | all |
| T15 | register says overweight, weighbridge says not; OWS billed anyway | hidden B only |
| T16 | per-shipment fee billed once per container | hidden B only |

The generator refuses to write a batch unless every trap lands with its
intended decision and reason, and unless hidden-only traps are absent from
every other batch. For the run-by-run effects it also requires, in every
batch: the detention invoice held for at least one run, an ADJUSTMENT on the
overweight invoice and on the invoice carrying the rolled container, and (in
B) the recovery of the register-weight overweight charge. The dates that make
these land are derived from the run calendar in `tools/generator/timeline.py`,
so they hold whatever weekday a batch's month starts on.

## 5. Ground truth, computed twice

`tools/generator/` builds each batch from an explicit, per-batch world:
register vs. controlling facts, contracts vs. ERP keying, notices,
circulars, invoices billed the way each vendor would, and the truth derived
from the policy. `solution/audit.py` is an independent reading of the same
rules, written against the documents (it parses the agreement PDFs and OCRs
the scans). It shares no code with the generator. Before any agent trial:

- agreement parsing matches the generator's contracts exactly (6 batches × 3 vendors)
- oracle output equals the truth on batches A and B, field by field, at
  every run (`tools/replay_check.py` replays a batch exactly as the verifier
  stages it)
- the oracle reproduces all four history ledgers, posting by posting
- each legacy defect changes at least one paid total. Only the fully correct
  detention rule fits every month: one month alone admits a half-fix,
  another rules it out
- regenerating any batch is byte-identical, scans included

## 6. Verifier

- `tests/Dockerfile` bakes Python 3.13, pdfplumber, poppler, tesseract,
  pytest 9.1.1, pytest-json-ctrf 0.5.2, hidden batch B and both truth files.
  Nothing is fetched at verify time.
- `tests/test.sh` does four things in order:
  1. removes any pre-existing reward file
  2. makes the truth and batch B's inbox root-only
  3. for each of batch B's payment runs, stages the inbox folders that have
     arrived by that date and runs the agent's tool as the unprivileged
     `auditrun` user, under a timeout, reaping its processes after each run
  4. runs pytest as root, with a binary reward

  The agent's `requirements.txt` is never installed, which closes the
  pytest-plugin autoload route.
- Tests compare exactly at cents: every run's postings and held invoices,
  then, after the last run, status, matching, paid to date, every line's
  amounts, decision and reason, landed cost, and reconciliation. They are grouped per
  trap so failures can be attributed. Exact comparison is fair because the
  policy fixes the rounding point and the largest-remainder tie-break.

## 7. Resources

2 CPUs / 4 GB; agent timeout 28 800 s (every merged Operations task uses
8 h); verifier timeout 900 s (the oracle's 12 runs on batch B, OCR
included, take about 20 s; each run is capped at 120 s).
