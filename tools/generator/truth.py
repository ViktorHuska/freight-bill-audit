"""Derives ground truth from the world and the invoice set, by the policy.

This is the generator's side of the two independent computations. It never asks
an invoice what it thinks the answer is: every expected amount, decision and
reason is recomputed here from the controlling facts (policy §2) and the
contract. The trap tags on lines are carried through only so the verifier can
group assertions per trap.
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Optional

import pricing
from models import ChargeLine, Invoice, World, category_of

D = Decimal
TOL = D("2.00")
PER_CONTAINER_CODES = {"OFR", "BAF", "THC_O", "THC_D", "SEAL", "OWS", "DET"}


# ------------------------------------------------------------- matching ----
def booking_for_line(world: World, inv: Invoice, line: ChargeLine):
    """Policy §2/§6: containers decide, then B/L, then the booking reference."""
    if line.container_no:
        try:
            return world.booking(world.container(line.container_no).act_booking_id)
        except KeyError:
            return None
    for b in world.bookings:
        if line.bl_number and b.bl_number == line.bl_number:
            return b
    for b in world.bookings:
        if inv.bl_ref and b.bl_number == inv.bl_ref:
            return b
        if inv.booking_ref and b.booking_id == inv.booking_ref:
            return b
    return None


def matched_bookings(world: World, inv: Invoice) -> list[str]:
    ids = {b.booking_id for b in (booking_for_line(world, inv, l) for l in inv.lines) if b}
    return sorted(ids)


# ------------------------------------------------------------- expected ----
def expected_usd(world: World, inv: Invoice, line: ChargeLine, booking) -> Optional[Decimal]:
    """Policy §3. Returns None when the contract does not list the code, which
    §3.8 turns into an unauthorised charge."""
    if booking is None:
        return None
    sail = booking.act_sailing
    vendor = inv.vendor
    code = line.charge_code
    ctype = world.container(line.container_no).ctype if line.container_no else "20DV"

    if code == "OFR":
        amt = pricing.ocean_freight(world, booking, ctype)
    elif code in ("BAF", "EIS"):
        amt = pricing.index_surcharge(world, booking, code, ctype)
        if amt is None:
            return None
    elif code == "OWS":
        v = pricing.version_for(world, vendor, sail)
        if not v.overweight:
            return None
        amt = pricing.overweight(world, booking, world.container(line.container_no))
    elif code == "DET":
        got = pricing.accessorial(world, vendor, code, ctype, booking.lane, sail)
        if got is None:
            return None
        amt = pricing.detention(world, booking, world.container(line.container_no))
    else:
        got = pricing.accessorial(world, vendor, code, ctype, booking.lane, sail)
        if got is None:
            return None
        _, amt = got
    return pricing.to_usd(world, inv.currency, amt, sail)


def basis_of(world: World, vendor: str, code: str, sail) -> str:
    v = pricing.version_for(world, vendor, sail)
    entry = v.accessorials.get(code)
    if entry is None:
        return "per_container"
    return entry[0]


# ----------------------------------------------------------- duplicates ----
def _fingerprint(world: World, inv: Invoice):
    return (
        inv.vendor,
        tuple(sorted((l.charge_code, l.container_no or "") for l in inv.lines)),
        pricing.q(inv.total),
    )


def find_duplicates(world: World, invoices: list[Invoice]) -> dict[str, str]:
    """Policy §5.1 -> {duplicate invoice_number: original invoice_number}."""
    out: dict[str, str] = {}
    seen: dict[tuple, Invoice] = {}
    for inv in sorted(invoices, key=lambda i: (i.invoice_date, i.invoice_number)):
        if inv.is_credit_note:
            continue
        fp = _fingerprint(world, inv)
        if fp in seen:
            out[inv.invoice_number] = seen[fp].invoice_number
        else:
            seen[fp] = inv
    return out


# -------------------------------------------------------------- deciding ---
def decide(inv: Invoice, line: ChargeLine, billed: Decimal, expected: Optional[Decimal],
           *, duplicate: bool, unmatched: bool, basis_excess: bool) -> tuple[Decimal, str, str]:
    """Policy §4, first matching row. Returns (expected, decision, reason)."""
    if duplicate:
        return D("0.00"), "DISPUTE", "DUPLICATE_INVOICE"
    if inv.is_credit_note:
        return billed, "APPROVE", "CREDIT_NOTE"
    if unmatched:
        return D("0.00"), "DISPUTE", "UNMATCHED"
    if expected is None:
        return D("0.00"), "DISPUTE", "UNAUTHORIZED_CHARGE"
    if basis_excess:
        return D("0.00"), "DISPUTE", "BASIS_ERROR"
    variance = billed - expected
    if line.charge_code == "DET" and variance > TOL:
        return expected, "DISPUTE", "FREE_TIME_MISCOUNT"
    if variance < -TOL:
        return expected, "APPROVE", "UNDERBILLED"
    if abs(variance) <= TOL and variance != 0:
        return expected, "APPROVE", "WITHIN_TOLERANCE"
    if variance == 0:
        return expected, "APPROVE", "OK"
    return expected, "DISPUTE", "RATE_MISMATCH"


# ------------------------------------------------------------ allocation ---
def _line_weights(world: World, line: ChargeLine, booking) -> list[tuple[str, Fraction]]:
    """Policy §7.2/§7.3: sales order -> exact share of one charge line."""
    if line.charge_code in PER_CONTAINER_CODES and line.container_no:
        containers = [world.container(line.container_no)]
    else:
        containers = world.containers_of(booking.booking_id)
        if line.bl_number:
            containers = [c for c in containers
                          if world.booking(c.act_booking_id).bl_number == line.bl_number]
    if not containers:
        return []
    per_container = Fraction(1, len(containers))
    weights: dict[str, Fraction] = {}
    for c in containers:
        total_kg = sum(sl.gross_kg for sl in c.lines)
        if total_kg == 0:
            continue
        for sl in c.lines:
            share = per_container * Fraction(sl.gross_kg, total_kg)
            weights[sl.so] = weights.get(sl.so, Fraction(0)) + share
    return sorted(weights.items())


def allocate_line(amount: Decimal, weights: list[tuple[str, Fraction]]) -> dict[str, Decimal]:
    """Largest remainder at cents; ties go to the lower sales_order (policy §7.4)."""
    if not weights or amount == 0:
        return {}
    sign = -1 if amount < 0 else 1
    cents = int((abs(amount) * 100).to_integral_value())
    exact = [(so, Fraction(cents) * w) for so, w in weights]
    floors = [(so, int(v)) for so, v in exact]
    remainder = cents - sum(v for _, v in floors)
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i][1] - floors[i][1]), exact[i][0]))
    take = {i: 0 for i in range(len(exact))}
    for i in order[:remainder]:
        take[i] = 1
    return {
        so: D(sign * (floors[i][1] + take[i])) / D(100)
        for i, (so, _) in enumerate(exact)
        if floors[i][1] + take[i] != 0
    }


# --------------------------------------------------------------- evaluate --
def _held(world: World, inv: Invoice) -> bool:
    """Policy §8: detention is paid on the terminal's reported empty return
    only. Until it is on file for every DET line, the invoice waits."""
    for l in inv.lines:
        if l.charge_code == "DET" and l.container_no:
            try:
                c = world.container(l.container_no)
            except KeyError:
                continue
            if c.act_empty_return is None:
                return True
    return False


def evaluate(world: World, invoices: list[Invoice]) -> dict[str, dict]:
    """One audit of the invoices on file against the facts on file.

    Returns {invoice_number: {"record", "held", "lines": [(approved, category,
    weights or None)]}}; weights are the allocation shares on these facts."""
    duplicates = find_duplicates(world, invoices)
    out: dict[str, dict] = {}

    for inv in invoices:
        bookings = matched_bookings(world, inv)
        unmatched = not bookings
        dup_of = duplicates.get(inv.invoice_number)
        held = (dup_of is None and not inv.is_credit_note and not unmatched
                and _held(world, inv))
        seen_per_bl: set[tuple[str, str]] = set()
        out_lines, alloc = [], []
        billed_total = D("0.00")
        approved_total = D("0.00")

        for n, line in enumerate(inv.lines, 1):
            booking = booking_for_line(world, inv, line)
            sail = booking.act_sailing if booking else inv.invoice_date
            billed = pricing.to_usd(world, inv.currency, line.amount, sail)
            billed_total += billed
            if held:
                out_lines.append({
                    "line_no": n, "charge_code": line.charge_code,
                    "container_no": line.container_no, "bl_number": line.bl_number,
                    "billed_amount_original": float(line.amount),
                    "billed_amount": float(billed), "expected_amount": None,
                    "variance": None, "decision": "HOLD", "reason": "AWAITING_EVIDENCE",
                })
                continue

            basis_excess = False
            if booking is not None and not unmatched:
                basis = basis_of(world, inv.vendor, line.charge_code, sail)
                if basis in ("per_bl", "per_shipment"):
                    unit = ((line.bl_number or booking.bl_number) if basis == "per_bl"
                            else booking.booking_id)
                    key = (line.charge_code, unit)
                    if key in seen_per_bl:
                        basis_excess = True
                    else:
                        seen_per_bl.add(key)

            exp = expected_usd(world, inv, line, booking)
            exp, decision, reason = decide(
                inv, line, billed, exp,
                duplicate=dup_of is not None, unmatched=unmatched, basis_excess=basis_excess,
            )
            approved = billed if decision == "APPROVE" else exp
            approved_total += approved

            out_lines.append({
                "line_no": n,
                "charge_code": line.charge_code,
                "container_no": line.container_no,
                "bl_number": line.bl_number,
                "billed_amount_original": float(line.amount),
                "billed_amount": float(billed),
                "expected_amount": float(exp),
                "variance": float(pricing.q(billed - exp)),
                "decision": decision,
                "reason": reason,
            })
            allocatable = booking is not None and not unmatched and dup_of is None
            alloc.append((approved, category_of(line.charge_code),
                          _line_weights(world, line, booking) if allocatable else None))

        if held:
            status = "HELD"
        elif dup_of is not None:
            status = "DUPLICATE"
        elif inv.is_credit_note:
            status = "CREDIT_NOTE"
        elif unmatched:
            status = "UNMATCHED"
        elif all(l["decision"] == "APPROVE" for l in out_lines):
            status = "APPROVED"
        elif all(l["decision"] == "DISPUTE" for l in out_lines):
            status = "DISPUTED"
        else:
            status = "PARTIALLY_DISPUTED"

        out[inv.invoice_number] = {
            "held": held,
            "lines": alloc,
            "record": {
                "invoice_number": inv.invoice_number,
                "vendor": inv.vendor,
                "invoice_date": inv.invoice_date.isoformat(),
                "currency": inv.currency,
                "status": status,
                "duplicate_of": dup_of,
                "matched_bookings": bookings,
                "invoice_total_usd": float(pricing.q(billed_total)),
                "approved_total_usd": float(pricing.q(approved_total)),
                "lines": out_lines,
            },
        }
    return out


# ----------------------------------------------------------------- derive --
CATS = ("ocean_freight", "surcharges", "accessorials", "detention")


def derive(world: World, invoices: list[Invoice], runs, visible_world) -> dict:
    """Replay the payment runs (policy §8). At each run the invoices on file are
    audited on the facts on file; a first decision is a PAYMENT, a later change
    in any line's approved amount an ADJUSTMENT. Each posting is allocated on
    the facts on file when it is made and never re-allocated."""
    all_sos = sorted({sl.so for c in world.containers for sl in c.lines})
    landed = {so: {k: D("0.00") for k in CATS} for so in all_sos}
    paid: dict[str, list[Decimal]] = {}
    run_out = []
    ev: dict[str, dict] = {}

    for run_date in runs:
        w = visible_world(run_date)
        on_file = [i for i in invoices if i.invoice_date <= run_date]
        ev = evaluate(w, on_file)
        postings, held = [], []
        for inv in sorted(on_file, key=lambda i: i.invoice_number):
            e = ev[inv.invoice_number]
            no = inv.invoice_number
            if e["held"]:
                assert no not in paid, f"{no} was paid and then held"
                held.append(no)
                continue
            now = [a for a, _, _ in e["lines"]]
            if no not in paid:
                kind, deltas = "PAYMENT", now
            else:
                deltas = [a - b for a, b in zip(now, paid[no])]
                if not any(deltas):
                    continue
                kind = "ADJUSTMENT"
            paid[no] = now
            for delta, (_, cat, weights) in zip(deltas, e["lines"]):
                if delta and weights:
                    for so, amt in allocate_line(delta, weights).items():
                        landed[so][cat] += amt
            postings.append({"invoice_number": no, "vendor": inv.vendor, "kind": kind,
                             "amount_usd": float(pricing.q(sum(deltas, D("0"))))})
        run_out.append({"run_date": run_date.isoformat(), "postings": postings, "held": held})

    audit, trap_index = [], {}
    for inv in sorted(invoices, key=lambda i: i.invoice_number):
        rec = dict(ev[inv.invoice_number]["record"])
        rec["paid_to_date_usd"] = float(pricing.q(sum(paid.get(inv.invoice_number, []), D("0"))))
        audit.append(rec)
        for n, line in enumerate(inv.lines, 1):
            if line.trap:
                trap_index.setdefault(line.trap, []).append([inv.invoice_number, n])

    landed_out = {}
    for so in all_sos:
        cats = landed[so]
        landed_out[so] = {k: float(v) for k, v in cats.items()}
        landed_out[so]["total"] = float(sum(cats.values()))

    return {
        "audit": {"batch": "inbox", "invoices": audit},
        "landed_cost": landed_out,
        "runs": run_out,
        "trap_index": {k: v for k, v in sorted(trap_index.items())},
    }
