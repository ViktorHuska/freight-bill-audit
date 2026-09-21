# terminal-bench/freight-bill-audit

<!-- The four sections below must be written by the author in their own words
     (CI runs an AI-detection check on task prose). The bullet notes are the
     points each section has to cover; replace them with prose. -->

## Difficulty explanation

<!-- Cover: rules are individually simple but coupled (sailing-month index, contract
     version by sailing date, working-day detention with holidays, per-B/L basis,
     FX date rule); two traps are legitimate charges that look wrong (minimum,
     overweight) so over-disputing fails too; reason-code attribution requires
     recomputing under alternative assumptions; landed-cost allocation cascades
     from every decision; the tool must generalise to an unseen batch. Why a junior
     AP clerk gets these wrong and an experienced freight auditor does not. -->

## Solution explanation

<!-- Cover: solution/audit.py — layout-specific pdfplumber parsers; matching
     order B/L -> booking -> containers; contract version by sailing date;
     expected amount per §3; attribution by single-assumption recomputation;
     duplicate/credit handling; status; largest-remainder allocation. Roughly how
     long it took you to write once the rules were clear (this is the
     expert_time_estimate_hours evidence). -->

## Verification explanation

<!-- Cover: separate verifier image bakes hidden batch B and truth for both
     batches; test.sh runs the agent's tool on batch B as an unprivileged user
     with truth root-only; tests compare cents exactly on decisions, reasons,
     expected amounts, matching, status, landed cost; per-trap parametrised tests
     for failure attribution; reconciliation invariants; binary reward. Why a
     hardcoded batch-A answer scores 0. -->

## Relevant experience

<!-- Your own words: export-sales office internship, freight-bill automation and
     shipping-document workflows you built, what an auditor there actually does. -->
