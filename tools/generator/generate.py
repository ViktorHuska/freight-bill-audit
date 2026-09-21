"""Orchestrator: seed -> world -> clean invoices -> traps -> PDFs + data + truth.

Usage (from repo root):
    python tools/generator/generate.py --batch a --seed 20240301 \
        --data-out tasks/freight-bill-audit/environment/data \
        --truth-out tasks/freight-bill-audit/tests/data/truth/batch_a.json
    python tools/generator/generate.py --batch b --seed 20240902 \
        --data-out tasks/freight-bill-audit/tests/data/batch_b \
        --truth-out tasks/freight-bill-audit/tests/data/truth/batch_b.json

Both batches share the vendor set, layouts and contract *families*; the second
uses different bookings, dates, index rows and trap placements. policy.md is
copied verbatim into both batches so the tool sees an identical rulebook.

Pipeline stages (each a function so they can be unit-tested in isolation):
    world.build(seed)         -> World
    invoices.clean(world)     -> list[Invoice]  (every line correct, APPROVE/OK)
    traps.plant_all(...)      -> mutates invoices, adds clones (T06/T07)
    truth.derive(...)         -> status per invoice, landed_cost per SO
    render.write_pdfs(...)    -> invoices/*.pdf in vendor layouts
    io.write_data(...)        -> shipments.json, contracts/*.json, holidays.json, fx.csv
    io.write_truth(...)       -> truth JSON (audit.json + landed_cost rows + trap index)
    selfcheck(...)            -> invariants (below)

Self-check invariants (fail loudly; never commit data that violates them):
    * every trap in traps.REGISTRY planted >= min_per_batch
    * every invoice number unique; every container on an invoice exists in the register
    * allocation shares per line sum exactly to the line's approved amount (cents)
    * landed_cost totals == sum of approved amounts across the batch (cents)
    * re-running with the same seed reproduces byte-identical data + truth
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

from models import World
import traps

POLICY_SRC = Path(__file__).resolve().parents[2] / "tasks/freight-bill-audit/environment/data/policy.md"

# Vendor set shared by both batches. Codes are what contracts/*.json use.
VENDORS = {
    "NORDVIK":    dict(kind="carrier",   currency="USD", layout="table"),      # tabular invoice
    "MERIDIAN":   dict(kind="carrier",   currency="USD", layout="keyvalue"),   # label: value blocks
    "ATLASOCEAN": dict(kind="carrier",   currency="EUR", layout="lines"),      # one charge per line, EUR
    "HARBORLINK": dict(kind="forwarder", currency="USD", layout="consolidated"),  # multi-B/L statements
}

# Lanes: US Gulf/East Coast exports to Middle East / South Asia (transshipment-heavy).
LANES = ["USSAV-AEJEA", "USHOU-AEJEA", "USSAV-SAJED", "USHOU-PKQCT", "USNYC-AEJEA"]
TERMINALS = {"AEJEA": ["AEJEA-T1", "AEJEA-T2"], "SAJED": ["SAJED-KCT"], "PKQCT": ["PKQCT-QICT"]}


def build_world(seed: int, batch: str) -> World:
    """Deterministic world. Sizes: ~14 bookings, ~40 containers, ~25 sales orders.

    Must guarantee the preconditions the traps need (see traps.py docstrings):
      * >=1 booking straddling a contract version boundary (T02)
      * >=1 `working`-mode terminal with a holiday inside a detention window (T03)
      * >=1 lane/ctype below minimum OFR (T05)
      * >=1 EUR booking where sailing-date and invoice-date fixings differ (T08)
      * >=1 sales order split across two bookings (T10)
      * >=1 container with booked_kg < threshold < gross_kg (T12)
    """
    rng = random.Random(seed)
    raise NotImplementedError("build_world: implement per docstring")


def clean_invoices(world: World, rng: random.Random) -> list:
    """One or more correct invoices per booking: carrier bills OFR+BAF+THC_O+SEAL+DOC
    (+DET where applicable); forwarder bills THC_D+DOC for a subset of B/Ls.
    Every line gets expected_usd from pricing.* and decision APPROVE/OK."""
    raise NotImplementedError


def derive_truth(world: World, invoices: list) -> dict:
    """Status per invoice (policy §6), approved totals, allocation (policy §7),
    landed_cost rows, plus a `trap_index` mapping trap id -> [(invoice, line_no)]
    used by tests to group assertions per trap."""
    raise NotImplementedError


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", choices=["a", "b"], required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--data-out", type=Path, required=True)
    ap.add_argument("--truth-out", type=Path, required=True)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    world = build_world(args.seed, args.batch)
    invoices = clean_invoices(world, rng)
    counts = traps.plant_all(world, invoices, rng)
    truth = derive_truth(world, invoices)

    import render, io_utils  # noqa: E402  (local modules)
    args.data_out.mkdir(parents=True, exist_ok=True)
    io_utils.write_data(world, args.data_out)
    render.write_pdfs(invoices, args.data_out / "invoices")
    shutil.copy(POLICY_SRC, args.data_out / "policy.md")
    args.truth_out.parent.mkdir(parents=True, exist_ok=True)
    args.truth_out.write_text(json.dumps(truth, indent=2, sort_keys=True))
    print(f"batch {args.batch}: {len(invoices)} invoices, traps={counts}")


if __name__ == "__main__":
    main()
