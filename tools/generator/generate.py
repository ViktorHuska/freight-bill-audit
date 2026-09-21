"""Orchestrator: batch -> world -> invoices -> truth -> PDFs + data files.

Usage (from the repo root):
    python tools/generator/generate.py --batch a \
        --data-out tasks/freight-bill-audit/environment/data \
        --truth-out tasks/freight-bill-audit/tests/data/truth/batch_a.json
    python tools/generator/generate.py --batch b \
        --data-out tasks/freight-bill-audit/tests/data/batch_b \
        --truth-out tasks/freight-bill-audit/tests/data/truth/batch_b.json

Both batches share vendors, layouts and contract families; they differ in
period, ids, rates and index rows. `policy.md` is copied verbatim into both so
the tool sees an identical rulebook.

The self-check below is the gate: it asserts every trap landed with the outcome
the trap intends, and that the allocation reconciles to the cent. Never commit
data that fails it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import invoices as invoices_mod  # noqa: E402
import io_utils  # noqa: E402
import render  # noqa: E402
import truth as truth_mod  # noqa: E402
from world import BatchSpec, build_world  # noqa: E402

# The canonical policy lives with the generator, OUTSIDE the task directory and
# the regenerated data: --data-out is wiped on every run, and the task should
# carry only the two byte-identical shipped copies (batch A and batch B).
POLICY_SRC = Path(__file__).resolve().parent / "policy.md"

# What each trap must produce. The generator refuses to write a batch whose
# traps did not land exactly like this.
EXPECTED = {
    "T01": ("DISPUTE", "RATE_MISMATCH"),
    "T02": ("DISPUTE", "RATE_MISMATCH"),
    "T03": ("DISPUTE", "RATE_MISMATCH"),
    "T04": ("DISPUTE", "FREE_TIME_MISCOUNT"),
    "T05": ("DISPUTE", "BASIS_ERROR"),
    "T06": ("APPROVE", "OK"),
    "T07": ("APPROVE", "OK"),
    "T08": ("APPROVE", "OK"),
    "T09": ("DISPUTE", "UNAUTHORIZED_CHARGE"),
    "T10": ("DISPUTE", "DUPLICATE_INVOICE"),
    "T11": ("APPROVE", "CREDIT_NOTE"),
    "T12": ("DISPUTE", "UNMATCHED"),
    "T13": ("APPROVE", "OK"),
    "T14": ("APPROVE", "OK"),
    "T15": ("DISPUTE", "RATE_MISMATCH"),
    "T16": ("DISPUTE", "BASIS_ERROR"),
}


# Cases that exist only in the hidden batch B (seed 2490): they exercise code
# paths the visible data never does, so a tool fitted to what it can see fails.
HIDDEN_ONLY = {"T15", "T16"}


def selfcheck(world, invs, truth: dict) -> None:
    by_inv = {i["invoice_number"]: i for i in truth["audit"]["invoices"]}

    numbers = [i.invoice_number for i in invs]
    assert len(numbers) == len(set(numbers)), "duplicate invoice numbers"

    for trap, (want_decision, want_reason) in EXPECTED.items():
        planted = truth["trap_index"].get(trap, [])
        if trap in HIDDEN_ONLY and world.seed != 2490:
            assert not planted, f"{trap} is hidden-batch only but was planted in seed {world.seed}"
            continue
        assert planted, f"{trap} was not planted"
        for inv_no, line_no in planted:
            line = by_inv[inv_no]["lines"][line_no - 1]
            got = (line["decision"], line["reason"])
            assert got == (want_decision, want_reason), (
                f"{trap} at {inv_no}#{line_no}: expected {(want_decision, want_reason)}, got {got}"
            )

    # The rolled container must be audited against the booking it actually moved
    # under, not the one the register still shows (policy §2).
    rolled = [c for c in world.containers if c.reassigned]
    assert rolled, "no container was rolled; T06 has no teeth"
    for c in rolled:
        for inv in truth["audit"]["invoices"]:
            if any(l["container_no"] == c.container_no for l in inv["lines"]):
                assert c.act_booking_id in inv["matched_bookings"], (
                    f"{inv['invoice_number']} matched {inv['matched_bookings']}, "
                    f"expected the rolled container's booking {c.act_booking_id}"
                )

    approved = sum(Decimal(str(i["approved_total_usd"])) for i in truth["audit"]["invoices"])
    landed = sum(Decimal(str(row["total"])) for row in truth["landed_cost"].values())
    assert approved == landed, f"landed cost {landed} != approved total {approved}"

    for inv in truth["audit"]["invoices"]:
        lines_sum = sum(
            Decimal(str(l["billed_amount"] if l["decision"] == "APPROVE" else l["expected_amount"]))
            for l in inv["lines"]
        )
        assert Decimal(str(inv["approved_total_usd"])) == lines_sum, inv["invoice_number"]

    for row in truth["landed_cost"].values():
        parts = sum(Decimal(str(row[k])) for k in
                    ("ocean_freight", "surcharges", "accessorials", "detention"))
        assert parts == Decimal(str(row["total"])), "category total mismatch"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", choices=["a", "b", "h1", "h2", "h3", "h4"], required=True)
    ap.add_argument("--data-out", type=Path, required=True)
    ap.add_argument("--truth-out", type=Path, required=True)
    ap.add_argument("--ledger", action="store_true",
                    help="history batch: also write ap_ledger.csv (what AP paid per invoice)")
    args = ap.parse_args()

    spec = BatchSpec(args.batch)
    world = build_world(args.batch)
    invs = invoices_mod.build_invoices(world, spec)
    truth = truth_mod.derive(world, invs)
    selfcheck(world, invs, truth)

    if args.data_out.exists():
        shutil.rmtree(args.data_out)
    io_utils.write_data(world, args.data_out)
    render.write_pdfs(invs, args.data_out / "invoices")
    if args.ledger:
        # History ships the settled outcome only: one paid total per invoice,
        # never line-level decisions. That is all AP's ledger would hold, and it
        # keeps the evidence sparse enough that defects have to be reasoned out.
        io_utils.write_ledger(truth, args.data_out / "ap_ledger.csv")
    else:
        shutil.copy(POLICY_SRC, args.data_out / "policy.md")

    args.truth_out.parent.mkdir(parents=True, exist_ok=True)
    args.truth_out.write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8", newline="\n")

    disputed = sum(1 for i in truth["audit"]["invoices"] for l in i["lines"]
                   if l["decision"] == "DISPUTE")
    total_lines = sum(len(i["lines"]) for i in truth["audit"]["invoices"])
    print(f"batch {args.batch}: {len(invs)} invoices, {total_lines} lines "
          f"({disputed} disputed), {len(truth['landed_cost'])} sales orders, "
          f"traps {sorted(truth['trap_index'])}")


if __name__ == "__main__":
    main()
