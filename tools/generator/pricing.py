"""Planting-time pricing. This is the *generator's* reading of the policy.

`tasks/freight-bill-audit/solution/audit.py` re-implements the same rules from
`policy.md` alone. Agreement between the two is what the oracle run proves; a
disagreement means the policy is ambiguous or one side is wrong.

Everything here prices from the CONTROLLING facts (policy §2): `act_sailing`,
`act_booking_id`, `act_gross_kg`, `act_gate_out`, `act_empty_return`. Helpers
that deliberately price from the register instead carry a `_stale` suffix and
exist only so traps can produce a realistic wrong invoice.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from models import Booking, Container, ContractVersion, World

CENT = Decimal("0.01")
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def q(x: Decimal) -> Decimal:
    """Policy §3.10: round half-up to cents, once, at the end of the line."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- lookups --
def version_for(world: World, vendor: str, on: date) -> ContractVersion:
    for v in world.contracts[vendor].versions:
        if v.valid_from <= on <= v.valid_to:
            return v
    raise KeyError(f"no {vendor} contract version covers {on}")


def circular_override(world: World, vendor: str, code: str, lane: Optional[str],
                      on: date) -> Optional[Decimal | dict[str, Decimal]]:
    """Policy §3.2: the newest circular in force on `on` that revises this code
    for this lane. Returns None when no circular touches it."""
    best = None
    for c in world.circulars:
        if c.vendor != vendor or c.effective_from > on:
            continue
        for r in c.revisions:
            if r.charge_code != code:
                continue
            if r.lane is not None and r.lane != lane:
                continue
            if best is None or c.effective_from >= best[0]:
                best = (c.effective_from, r.amount)
    return None if best is None else best[1]


def _per_ctype(amount: Decimal | dict[str, Decimal], ctype: str) -> Decimal:
    return amount[ctype] if isinstance(amount, dict) else amount


# ------------------------------------------------------------------ rules --
def ocean_freight(world: World, booking: Booking, ctype: str, *, on: Optional[date] = None) -> Decimal:
    """Policy §3.4, including the minimum floor."""
    sail = on or booking.act_sailing
    v = version_for(world, booking.vendor, sail)
    rate = v.lanes[booking.lane][ctype]
    override = circular_override(world, booking.vendor, "OFR", booking.lane, sail)
    if override is not None:
        rate = _per_ctype(override, ctype)
    return max(rate, v.min_ofr.get(ctype, Decimal("0")))


def index_surcharge(world: World, booking: Booking, code: str, ctype: str,
                    *, on: Optional[date] = None) -> Optional[Decimal]:
    """Policy §3.5: the row for the month of the sailing date, unless a circular
    in force on that date revises it (§3.2)."""
    sail = on or booking.act_sailing
    v = version_for(world, booking.vendor, sail)
    table = v.index_surcharges.get(code)
    if table is None:
        return None
    override = circular_override(world, booking.vendor, code, booking.lane, sail)
    if override is not None:
        return _per_ctype(override, ctype)
    row = table.get(f"{sail.year}-{sail.month:02d}")
    return None if row is None else row[ctype]


def accessorial(world: World, vendor: str, code: str, ctype: str, lane: Optional[str],
                on: date) -> Optional[tuple[str, Decimal]]:
    """Returns (basis, amount) or None when the contract does not list the code
    (policy §3.8)."""
    v = version_for(world, vendor, on)
    entry = v.accessorials.get(code)
    if entry is None:
        return None
    basis, amount = entry
    override = circular_override(world, vendor, code, lane, on)
    if override is not None:
        amount = override
    return basis, _per_ctype(amount, ctype)


def overweight(world: World, booking: Booking, c: Container, *, use_register: bool = False) -> Decimal:
    """Policy §3.6: weighbridge weight decides, never the booked weight."""
    v = version_for(world, booking.vendor, booking.act_sailing)
    if not v.overweight:
        return Decimal("0")
    threshold, amounts = v.overweight
    kg = c.reg_gross_kg if use_register else c.act_gross_kg
    return amounts[c.ctype] if kg > threshold else Decimal("0")


def counted_days(world: World, c: Container, mode: str, start: date, end: date) -> int:
    """Policy §3.7. Day 1 is the day after gate-out; the empty-return day counts.
    `working` skips that terminal's own weekend days and its closures."""
    term = world.terminals[c.terminal]
    closures = set(term.closures)
    n = 0
    day = start + timedelta(days=1)
    while day <= end:
        if mode == "calendar":
            n += 1
        elif WEEKDAY_NAMES[day.weekday()] not in term.weekend and day not in closures:
            n += 1
        day += timedelta(days=1)
    return n


def detention(world: World, booking: Booking, c: Container, *,
              use_register_dates: bool = False, force_mode: Optional[str] = None,
              apply_free: bool = True) -> Decimal:
    """Policy §3.7. The keyword arguments exist so a trap can bill the way a
    careless vendor would (register dates, calendar counting, no free period)."""
    v = version_for(world, booking.vendor, booking.act_sailing)
    gate = c.reg_gate_out if use_register_dates else c.act_gate_out
    ret = c.reg_empty_return if use_register_dates else c.act_empty_return
    if gate is None or ret is None:
        return Decimal("0")
    mode = force_mode or v.terminal_modes[c.terminal]
    days = counted_days(world, c, mode, gate, ret)
    if apply_free:
        days = max(days - v.detention_free_days, 0)
    total = Decimal("0")
    for n in range(1, days + 1):
        for lo, hi, rates in v.detention_tiers:
            if n >= lo and (hi is None or n <= hi):
                total += rates[c.ctype]
                break
    return total


def detention_days(world: World, booking: Booking, c: Container) -> int:
    v = version_for(world, booking.vendor, booking.act_sailing)
    if c.act_gate_out is None or c.act_empty_return is None:
        return 0
    mode = v.terminal_modes[c.terminal]
    return max(counted_days(world, c, mode, c.act_gate_out, c.act_empty_return) - v.detention_free_days, 0)


# --------------------------------------------------------------------- fx --
def fx_rate(world: World, on: date) -> Decimal:
    """Policy §3.9: the fixing for the date, else the most recent earlier one."""
    day = on
    for _ in range(10):
        if day in world.fx:
            return world.fx[day]
        day -= timedelta(days=1)
    raise KeyError(f"no fixing on or before {on}")


def to_usd(world: World, currency: str, amount: Decimal, sailing: date) -> Decimal:
    if currency == "USD":
        return q(amount)
    return q(amount * fx_rate(world, sailing))


def to_invoice_ccy(world: World, currency: str, usd: Decimal, sailing: date) -> Decimal:
    if currency == "USD":
        return q(usd)
    return q(usd / fx_rate(world, sailing))
