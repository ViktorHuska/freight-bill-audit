# terminal-bench/freight-bill-audit

<!-- Write the four sections below yourself: TB3 requires them to be written
     completely by a human. One to three sentences each. The bullet notes in
     each comment are what the section must cover; replace the comment with
     your prose. -->

## Difficulty explanation

<!-- Cover:
     - The real job: a freight auditor at an exporter's sales office checking
       carrier and forwarder invoices before accounts payable releases them.
     - The core challenge: the ERP register is stale, and the correct facts are
       in other sources (carrier notices, the terminal move log, tariff
       circulars). The agent has to reconstruct them, and one wrong fact
       cascades: a sailing amendment moves the contract version, the surcharge
       month and the FX date together.
     - One real domain fact: terminals have their own weekends (Jeddah runs
       Fri/Sat), which a Mon-Fri assumption gets wrong.
     - Two legitimate charges that look wrong, so disputing everything fails.
     - The tool must generalise to an unseen batch.
     - One sentence on provenance: the data is synthetic, modelled on real
       ocean-freight invoices, tariffs and terminal practice.
     - One sentence on who does this in reality, and why a junior AP clerk
       gets it wrong where an experienced auditor does not.
     - No trial results or pass rates (the rubric forbids them). -->

## Solution explanation

<!-- Cover, as a summary, not a walkthrough:
     - solution/audit.py: pdfplumber parsers for three vendor layouts (US
       numbers, European numbers, grouped by B/L).
     - First establish the facts: apply notices by date over the register, and
       take the move log over the register for dates and weights.
     - Then price by policy section 3 (contract version by sailing date,
       circulars, minimum floor, index month, per-terminal working days, FX at
       the sailing-date fixing), decide by the section 4 table, and allocate by
       exact fractions plus the largest-remainder method.
     - How long it took you once the rules were clear (the evidence for
       expert_time_estimate_hours = 3). -->

## Verification explanation

<!-- Cover:
     - A separate verifier image bakes in hidden batch B and the truth for both
       batches.
     - test.sh makes the truth root-only, then runs the agent's tool on batch B
       as an unprivileged user.
     - Tests compare, exactly at cents, the status, matching, every line's
       amounts, decision and reason, and the landed cost. Exact comparison is
       fair because the policy fixes the rounding point and the tie-break.
     - Per-trap tests exist so failures can be attributed; reward is binary.
     - Truth is computed twice, independently (generator and oracle), and the
       two agree on both batches.
     - Why a hand-written answer for batch A scores 0. -->

## Relevant experience

<!-- Your own words: the export-sales-office internship, the freight-bill and
     shipping-document work you did there, and what an auditor there actually
     checks. -->
