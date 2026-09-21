"""Planting-time pricing helpers used by the world builder and the trap registry.

This is the *generator's* notion of the rules. The solution in
`tasks/freight-bill-audit/solution/audit.py` re-implements them independently from
`policy.md`. Agreement between the two is checked by the oracle run.

Keep this module small and literal: one function per policy rule, each citing
the policy section it implements.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from models import Booking, ChargeLine, Container, ContractVersion, Invoice, World

CENT = Decimal("0.01")


def q(x: Decimal) -> Decimal:
    """Policy §3.9: round half-up to cents, only at the end of a line."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


# ---- lookups ---------------------------------------------------------------
def booking_by_container(world: World, container_no: str) -> Optional[Booking]:
    for b in world.bookings:
        if any(c.container_no == container_no for c in b.containers):
            return b
    return None


def container(world: World, container_no: str) -> Container:
    for b in world.bookings:
        for c in b.containers:
            if c.container_no == container_no:
                return c
    raise KeyError(container_no)


def booking_for(world: World, inv: Invoice, line: ChargeLine) -> Optional[Booking]:
    """Policy §2: B/L first, then booking, then containers."""
    if line.bl_number:
        for b in world.bookings:
            if b.bl_number == line.bl_number:
                return b
    if line.container_no:
        return booking_by_container(world, line.container_no)
    for b in world.bookings:
        if inv.bl_ref and b.bl_number == inv.bl_ref:
            return b
        if inv.booking_ref and b.booking_id == inv.booking_ref:
            return b
    return None


def containers_on_invoice(world: World, inv: Invoice) -> list[Container]:
    seen, out = set(), []
    for l in inv.lines:
        if l.container_no and l.container_no not in seen:
            seen.add(l.container_no)
            out.append(container(world, l.container_no))
    return out


def version_for(world: World, vendor: str, on: date) -> ContractVersion:
    """Policy §3.1: version whose window contains the sailing date (or any date passed)."""
    for v in world.contracts[vendor].versions:
        if v.valid_from <= on <= v.valid_to:
            return v
    raise KeyError(f"no {vendor} contract version covers {on}")


# ---- rules -----------------------------------------------------------------
def ocean_freight(world: World, vendor: str, booking: Booking, ctype: str, on: Optional[date] = None) -> Decimal:
    """Policy §3.3 with minimum floor."""
    v = version_for(world, vendor, on or booking.sailing)
    rate = v.lanes[booking.lane][ctype]
    return max(rate, v.min_ofr.get(ctype, Decimal("0")))


def index_surcharge(world: World, booking: Booking, code: str, ctype: str,
                    period: Optional[date] = None) -> Optional[Decimal]:
    """Policy §3.4: row for the sailing month (period overridable for trap planting)."""
    v = version_for(world, booking.vendor, booking.sailing)
    table = v.index_surcharges.get(code)
    if not table:
        return None
    key = (period or booking.sailing).strftime("%Y-%m")
    row = table.get(key)
    return None if row is None else row[ctype]


def overweight(world: World, booking: Booking, c: Container) -> Decimal:
    """Policy §3.5: actual gross_kg vs threshold."""
    v = version_for(world, booking.vendor, booking.sailing)
    if v.overweight and c.gross_kg > v.overweight[0]:
        return v.overweight[1][c.ctype]
    return Decimal("0")


def detention_days(world: World, v: ContractVersion, c: Container,
                   mode: Optional[str] = None, apply_free: bool = True) -> int:
    """Policy §3.6. `mode`/`apply_free` overridable to plant FREE_TIME_MISCOUNT."""
    if not (c.gate_out and c.empty_return):
        return 0
    mode = mode or v.terminal_modes[c.terminal]
    hol = set(world.holidays.get(c.terminal, []))
    d, counted = c.gate_out + timedelta(days=1), 0
    while d <= c.empty_return:
        if mode == "calendar" or (d.weekday() < 5 and d not in hol):
            counted += 1
        d += timedelta(days=1)
    free = v.detention_free_days if apply_free else 0
    return max(counted - free, 0)


def detention(world: World, booking: Booking, c: Container, **kw) -> Decimal:
    v = version_for(world, booking.vendor, booking.sailing)
    days = detention_days(world, v, c, **kw)
    total = Decimal("0")
    for day in range(1, days + 1):
        for lo, hi, rates in v.detention_tiers:
            if day >= lo and (hi is None or day <= hi):
                total += rates[c.ctype]
                break
    return total


def fx_rate(world: World, on: date) -> Decimal:
    """Policy §3.8: fixing on the date, else most recent earlier fixing."""
    d = on
    while d not in world.fx:
        d -= timedelta(days=1)
    return world.fx[d]


def to_invoice_ccy(world: World, inv: Invoice, booking: Booking, usd: Decimal) -> Decimal:
    """Inverse of §3.8 for planting: express a USD amount in the invoice currency."""
    if inv.currency == "USD":
        return q(usd)
    return q(usd / fx_rate(world, booking.sailing))


def to_usd(world: World, inv: Invoice, booking: Booking, amt: Decimal, on: Optional[date] = None) -> Decimal:
    if inv.currency == "USD":
        return q(amt)
    return q(amt * fx_rate(world, on or booking.sailing))
