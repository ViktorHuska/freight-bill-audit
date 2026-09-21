"""Replay a batch through a tool run by run and diff it against the truth.

    python tools/replay_check.py --tool tasks/freight-bill-audit/solution/audit.py \
        --batch /path/to/batch --truth /path/to/truth.json [--ledger]

Dev tooling (not part of the task). Each run sees only the inbox folders that
have arrived by its date, exactly as the verifier stages them. With --ledger
the postings are compared against the batch's ap_ledger.csv instead.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", type=Path, required=True)
    ap.add_argument("--batch", type=Path, required=True)
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--ledger", action="store_true")
    args = ap.parse_args()

    runs = [l.strip() for l in (args.batch / "payment_runs.txt").read_text().splitlines()
            if l.strip() and not l.startswith("#")]
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        inbox, state, out = td / "inbox", td / "state", td / "out"
        inbox.mkdir()
        got_runs = []
        for r in runs:
            for day in sorted((args.batch / "inbox").iterdir()):
                if day.name <= r and not (inbox / day.name).exists():
                    shutil.copytree(day, inbox / day.name)
            cmd = [sys.executable, str(args.tool), "--inbox", str(inbox),
                   "--shipments", str(args.batch / "shipments.json"),
                   "--contracts", str(args.batch / "contracts"),
                   "--holidays", str(args.batch / "holidays.json"),
                   "--fx", str(args.batch / "fx.csv"), "--policy", str(args.batch / "policy.md"),
                   "--state", str(state), "--run-date", r, "--out", str(out)]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode:
                print(f"run {r} failed:\n{p.stderr[-2000:]}")
                return 1
            got_runs.append(json.loads((out / "runs" / f"{r}.json").read_text()))
        audit = json.loads((out / "audit.json").read_text())
        with (out / "landed_cost.csv").open() as f:
            landed = {row["sales_order"]: row for row in csv.DictReader(f)}

    if args.ledger:
        with (args.batch / "ap_ledger.csv").open() as f:
            want = [(r["run_date"], r["invoice_number"], r["kind"], float(r["amount_usd"]))
                    for r in csv.DictReader(f)]
        got = [(r["run_date"], p["invoice_number"], p["kind"], p["amount_usd"])
               for r in got_runs for p in r["postings"]]
        for w in want:
            if w not in got:
                print("  ledger posting missing/different:", w)
                bad += 1
        for g in got:
            if g not in want:
                print("  extra posting:", g)
                bad += 1
        print(f"{args.batch.name}: ledger {'OK' if not bad else f'{bad} mismatches'} "
              f"({len(want)} postings)")
        return 1 if bad else 0

    truth = json.loads(args.truth.read_text())
    for w, g in zip(truth["runs"], got_runs):
        if w != g:
            bad += 1
            print(f"  run {w['run_date']}:\n    want {w}\n    got  {g}")
    want_inv = {i["invoice_number"]: i for i in truth["audit"]["invoices"]}
    for inv in audit["invoices"]:
        w = dict(want_inv.get(inv["invoice_number"], {}))
        for k in w:
            if k == "lines":
                for wl, gl in zip(w["lines"], inv["lines"]):
                    if wl != gl:
                        bad += 1
                        print(f"  {inv['invoice_number']}#{wl['line_no']}:\n    want {wl}\n    got  {gl}")
            elif w[k] != inv.get(k):
                bad += 1
                print(f"  {inv['invoice_number']}.{k}: want {w[k]} got {inv.get(k)}")
    for so, row in truth["landed_cost"].items():
        for k, v in row.items():
            if abs(float(landed[so][k]) - v) > 0.001:
                bad += 1
                print(f"  landed {so}.{k}: want {v:.2f} got {landed[so][k]}")
    print(f"{args.batch.name}: {'OK' if not bad else f'{bad} mismatches'} ({len(runs)} runs)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
