# Design: `freight-bill-audit`

The decisions behind the task, for the repository reader and the interview.
Nothing here ships into the task directory. The iteration history, with the
trial evidence that drove each change, is in [RESULTS.md](RESULTS.md).

## 1. The job

A freight auditor at an exporter's international sales office checks every
ocean-freight invoice (from two carriers and a forwarder) before accounts
payable releases it, and allocates the approved cost to sales orders. The
agent does that job by building a reusable tool:

| Artifact | Purpose |
|---|---|
| `/app/audit.py` | Single-file CLI that audits a month's batch |
| `/app/output/audit.json` | Per-invoice status and per-line billed / expected / variance / decision / reason |
| `/app/output/landed_cost.csv` | Approved cost per sales order, by category |

**The deliverable is a tool, not answers.** The verifier re-runs `audit.py`,
unchanged, on a hidden batch B. A hand-written answer for the visible batch
scores zero.

## 2. What the agent is given

```
/app/data/              this month's batch
  invoices/*.pdf          text PDFs (two carriers) and SCANNED statements (forwarder)
  shipments.json          ERP booking register export (stale on purpose)
  terminal_moves.csv      terminal gate dates and weighbridge weights
  notices/*.txt           sailing amendments, container rolls, tariff circulars
  contracts/<V>_agreement.pdf   signed rate agreement (authoritative)
  contracts/<V>.json            the ERP's hand-keyed copy (has keying errors)
  holidays.json, fx.csv   terminal weekends + closures, EUR/USD fixings
  policy.md               decision table, duplicates, allocation, schema
/app/legacy/audit_legacy.py   the desk's current tool, with realistic defects
/app/history/h1..h4/          four settled months, each with ap_ledger.csv
```

`policy.md` deliberately does **not** state the pricing doctrine. Instead it
says the legacy tool implements how the desk prices charges, that the tool
is not always right, and that what AP actually paid, recorded in the
history ledgers after the senior auditor's review, is authoritative.

## 3. Where the difficulty is meant to be

Three layers, each taken from a pattern in merged TB3 Operations tasks:

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

   The only feedback is per-invoice paid totals in four settled months. The
   ERP keying errors differ every month, so nothing can be hardcoded.
3. **Domain rules that only a careful expert applies.**
   - Terminals keep their own weekends (Jeddah's is Friday/Saturday).
   - The US-trade notice clause: a rate increase takes effect no earlier
     than 30 days after publication, a decrease immediately. A THC increase
     published 8 days ahead applies to one booking and not to two others.
   - A per-B/L fee on a two-carrier forwarder consolidation is due once per
     B/L, not once per invoice.

The hidden batch adds four cases that never occur in the visible data or
the history, each defined by the documents: superseding notices whose file
order contradicts their dates, a Sunday EUR sailing (FX falls back to the
Friday fixing), a per-shipment fee, and a weighbridge weight *below* the
overweight threshold. The forwarder's statements are scans, so reading them
needs OCR.

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
every other batch.

## 5. Ground truth, computed twice

`tools/generator/` builds each batch from an explicit, per-batch world:
register vs. controlling facts, contracts vs. ERP keying, notices,
circulars, invoices billed the way each vendor would, and the truth derived
from the policy. `solution/audit.py` is an independent reading of the same
rules, written against the documents (it parses the agreement PDFs and OCRs
the scans). It shares no code with the generator. Before any agent trial:

- agreement parsing matches the generator's contracts exactly (6 batches × 3 vendors)
- oracle output equals the truth on batches A and B, field by field
- the oracle reproduces all four history ledgers to the cent
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
  2. makes the truth root-only
  3. runs the agent's tool on batch B as the unprivileged `auditrun` user,
     under a timeout
  4. runs pytest as root, with a binary reward

  The agent's `requirements.txt` is never installed, which closes the
  pytest-plugin autoload route.
- Tests compare exactly at cents: status, matching, every line's amounts,
  decision and reason, landed cost, and reconciliation. They are grouped per
  trap so failures can be attributed. Exact comparison is fair because the
  policy fixes the rounding point and the largest-remainder tie-break.

## 7. Resources

2 CPUs / 4 GB; agent timeout 28 800 s (every merged Operations task uses
8 h); verifier timeout 900 s (OCR plus the tool on batch B finishes in well
under a minute).
