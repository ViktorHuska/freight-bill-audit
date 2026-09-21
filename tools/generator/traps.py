"""Trap registry.

A trap is a deliberate, realistic vendor error (or a *legitimate* charge that looks
like an error) planted on a clean invoice. Each trap:

  1. mutates the invoice/lines,
  2. records the expected outcome (expected_usd, decision, reason) on the lines it
     touched, computed here from the intended rule — independently of the
     solution's implementation,
  3. tags the lines and invoice with its id so tests can be grouped per trap.

`clean(world, inv)` must already have filled expected_usd for every line with the
correct value and decision APPROVE/OK before a trap is applied.

Implemented traps are the pattern; the stubs raise NotImplementedError and carry
the exact behaviour to implement, so the registry doubles as the spec.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable

from models import ChargeLine, Invoice, World
import pricing  # reference pricing used ONLY at planting time (generator side)

TrapFn = Callable[[World, Invoice, random.Random], bool]  # returns True if planted


@dataclass(frozen=True)
class Trap:
    id: str
    name: str
    min_per_batch: int
    fn: TrapFn


REGISTRY: list[Trap] = []


def trap(id: str, name: str, min_per_batch: int = 1):
    def deco(fn: TrapFn) -> TrapFn:
        REGISTRY.append(Trap(id, name, min_per_batch, fn))
        return fn
    return deco


def _lines_with(inv: Invoice, code: str) -> list[ChargeLine]:
    return [l for l in inv.lines if l.charge_code == code]


def _tag(inv: Invoice, lines: list[ChargeLine], tid: str) -> None:
    for l in lines:
        l.trap = tid
    if tid not in inv.traps:
        inv.traps.append(tid)


# ------------------------------------------------------------------------
# Implemented examples (pattern)
# ------------------------------------------------------------------------
@trap("T01", "BAF read from invoice month instead of sailing month", min_per_batch=2)
def t01_surcharge_period(world: World, inv: Invoice, rng: random.Random) -> bool:
    """Vendor prices BAF from the index row of the invoice month. Sailing was in the
    previous month and the index moved. Expected stays the sailing-month value;
    billed becomes the invoice-month value; reason WRONG_SURCHARGE_PERIOD."""
    lines = _lines_with(inv, "BAF")
    if not lines or inv.is_credit_note:
        return False
    booking = pricing.booking_for(world, inv, lines[0])
    if booking is None or booking.sailing.strftime("%Y-%m") == inv.invoice_date.strftime("%Y-%m"):
        return False
    ctr = pricing.container(world, lines[0].container_no)
    wrong = pricing.index_surcharge(world, booking, "BAF", ctr.ctype, period=inv.invoice_date)
    if wrong is None or wrong == lines[0].amount:
        return False
    for l in lines:
        l.amount = pricing.to_invoice_ccy(world, inv, booking, wrong)
        l.decision, l.reason = "DISPUTE", "WRONG_SURCHARGE_PERIOD"
        # expected_usd unchanged (correct sailing-month value already set by clean())
    _tag(inv, lines, "T01")
    return True


@trap("T04", "per-B/L documentation fee billed once per container", min_per_batch=2)
def t04_basis_error(world: World, inv: Invoice, rng: random.Random) -> bool:
    """Vendor lists DOC once per container. Policy §3.2: expected for the invoice is
    what per_bl yields once; the first DOC line keeps expected = fee, additional
    DOC lines get expected 0.00, all DOC lines reason BASIS_ERROR/DISPUTE except
    the first, which is APPROVE/OK when its amount equals the fee."""
    docs = _lines_with(inv, "DOC")
    if len(docs) != 1 or inv.is_credit_note:
        return False
    base = docs[0]
    containers = pricing.containers_on_invoice(world, inv)
    if len(containers) < 2:
        return False
    for c in containers[1:]:
        dup = ChargeLine("DOC", base.description, c.container_no, base.bl_number, base.amount,
                         expected_usd=Decimal("0.00"), decision="DISPUTE", reason="BASIS_ERROR")
        inv.lines.insert(inv.lines.index(base) + 1, dup)
    _tag(inv, [l for l in inv.lines if l.charge_code == "DOC" and l is not base], "T04")
    return True


# ------------------------------------------------------------------------
# Stubs — the spec for what remains to implement
# ------------------------------------------------------------------------
@trap("T02", "contract version chosen by invoice date")
def t02_contract_version(world, inv, rng):
    """Booking sailed inside version N's window; invoice dated inside version N+1.
    Vendor bills OFR at version N+1's lane rate. Expected = version N rate.
    Reason CONTRACT_VERSION (attribution: recomputing with invoice-date version
    reproduces billed). Requires the world to contain at least one booking whose
    sailing and invoice dates straddle a version boundary."""
    raise NotImplementedError


@trap("T03", "detention free time miscounted (mode/holidays)")
def t03_free_time(world, inv, rng):
    """Terminal in `working` mode with a holiday inside the detention window.
    Vendor counts calendar days (or forgets the free period). Expected = policy
    §3.6 count. Reason FREE_TIME_MISCOUNT only if one of the two alternative
    counts reproduces billed; otherwise this becomes RATE_MISMATCH — the
    generator must assert which one it planted."""
    raise NotImplementedError


@trap("T05", "minimum ocean freight applies — legitimate")
def t05_minimum_charge(world, inv, rng):
    """Lane rate below contract minimum; vendor correctly bills the minimum.
    No mutation of amount. Expected = minimum, decision APPROVE, reason OK.
    The trap is in the *world*: ensure at least one lane/ctype pair below minimum
    exists and is invoiced. Tag lines so the test can assert no false dispute."""
    raise NotImplementedError


@trap("T06", "duplicate invoice re-issued")
def t06_duplicate(world, inv, rng):
    """Clone the invoice with a new invoice_number and a later date (+9..+20 days),
    identical lines. Clone: status DUPLICATE, duplicate_of = original,
    every line DISPUTE/DUPLICATE_INVOICE with expected 0.00. The clone is
    appended to the batch by the orchestrator (return value carries it)."""
    raise NotImplementedError


@trap("T07", "credit note against an earlier invoice")
def t07_credit_note(world, inv, rng):
    """Emit a credit note (negative amounts) for one over-billed line of an
    invoice that carried a dispute. Credit note lines: APPROVE/CREDIT_NOTE,
    expected = billed (negative), status CREDIT_NOTE; allocation reduces
    landed cost."""
    raise NotImplementedError


@trap("T08", "EUR invoice converted at invoice-date fixing")
def t08_fx_date(world, inv, rng):
    """EUR vendor. Billed EUR is correct; the *test* is whether the tool converts
    at the sailing-date fixing. Plant by choosing bookings where the two fixings
    differ by > 2 USD on at least one line. No mutation; expected_usd computed at
    sailing-date rate; decision APPROVE/OK. Tag lines."""
    raise NotImplementedError


@trap("T09", "booking reference typo, containers still match")
def t09_booking_typo(world, inv, rng):
    """Transpose two digits in inv.booking_ref and drop bl_ref. Expected outcome:
    matched via containers (policy §2.2); all decisions unchanged; matched_bookings
    must equal the true booking. Tag invoice only."""
    raise NotImplementedError


@trap("T10", "split shipment: one sales order on two B/Ls")
def t10_split_shipment(world, inv, rng):
    """World-level trap: a sales order appears in containers on two bookings
    (possibly different vendors). Truth landed_cost sums both shares. Tag the
    lines on both invoices so the allocation test can isolate the SO."""
    raise NotImplementedError


@trap("T11", "charge code not in contract")
def t11_unauthorized(world, inv, rng):
    """Insert a plausible accessorial not in the vendor's contract (e.g.
    'CGS' congestion surcharge, or 'ISPS'). expected 0.00, DISPUTE,
    UNAUTHORIZED_CHARGE."""
    raise NotImplementedError


@trap("T12", "overweight surcharge triggered by packing-list weight — legitimate")
def t12_overweight(world, inv, rng):
    """Container booked below threshold, actual gross_kg above. Vendor bills OWS
    correctly. Expected = OWS amount, APPROVE/OK. World must guarantee such a
    container exists. Tag lines."""
    raise NotImplementedError


@trap("T13", "variance inside tolerance")
def t13_within_tolerance(world, inv, rng):
    """Nudge a THC line by ±0.50..1.99. Expected unchanged; decision APPROVE,
    reason WITHIN_TOLERANCE; approved amount = billed (policy §4)."""
    raise NotImplementedError


@trap("T14", "forwarder invoice spanning two carriers' bookings")
def t14_forwarder_consolidation(world, inv, rng):
    """Forwarder (HARBORLINK) invoice listing THC_D and DOC for two B/Ls that
    belong to different carriers. Pricing uses the *forwarder's* contract
    (policy §3.1: invoicing vendor), per_bl fees once per B/L. Naive tools price
    with the carrier's contract or apply one DOC for the whole invoice."""
    raise NotImplementedError


def plant_all(world: World, invoices: list[Invoice], rng: random.Random) -> dict[str, int]:
    """Apply every trap at least `min_per_batch` times across the batch, choosing
    candidate invoices at random but deterministically. Returns counts per trap.
    Raises if a trap could not be planted enough times (then fix the world)."""
    counts: dict[str, int] = {}
    for t in REGISTRY:
        planted = 0
        order = list(invoices)
        rng.shuffle(order)
        for inv in order:
            if planted >= t.min_per_batch:
                break
            if t.fn(world, inv, rng):
                planted += 1
        if planted < t.min_per_batch:
            raise RuntimeError(f"{t.id} planted {planted} < {t.min_per_batch}: adjust world generation")
        counts[t.id] = planted
    return counts
