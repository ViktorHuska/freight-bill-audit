"""When things become known: the inbox calendar, payment runs, and the world as
it looks on file at a given run date.

The month is audited as it happens (policy §8). Every document lands in the
inbox folder of the day it arrived; AP pays on fixed run dates, and a run sees
only what has arrived by then. The world built in `world.py` is the state of
affairs once everything is known; `visible_world` rolls it back to what was on
file at a run date, which is what truth for that run is priced from.
"""
from __future__ import annotations

import calendar
import copy
from datetime import date, timedelta

from models import Container, Invoice, World


# ------------------------------------------------------------ run calendar --
def payment_runs(first: date, last: date) -> list[date]:
    """AP pays every Friday and on the last calendar day of each month, from
    the first invoice's arrival to the month-end after the last one."""
    end = date(last.year, last.month, calendar.monthrange(last.year, last.month)[1])
    out = []
    day = first
    while day <= end:
        month_end = day.day == calendar.monthrange(day.year, day.month)[1]
        if day.weekday() == 4 or month_end:
            out.append(day)
        day += timedelta(days=1)
    return out


def arrival_of_row(world: World, c: Container) -> date:
    """The destination terminal reports a container (with its weighbridge
    weight) on discharge, at the ETA of the booking it actually moved under."""
    return world.booking(c.act_booking_id).eta


def schedule(world: World, invoices: list[Invoice], batch: str) -> list[date]:
    """Fix the arrival dates that the run calendar decides, and return the runs.

    Two traps depend on where an arrival falls relative to a run:
      * the b4 invoice (overweight on the weighbridge) is paid at a run BEFORE
        the terminal reports the container, so it is first priced on the
        register weight and corrected by a later ADJUSTMENT;
      * the b7 invoice (carrying the rolled container) is paid at a run BEFORE
        the roll advice arrives, which comes the day after.
    """
    by_no = {i.invoice_number: i for i in invoices}
    tag = batch.upper()
    first = min(i.invoice_date for i in invoices)
    last = max(i.invoice_date for i in invoices)
    runs = payment_runs(first, last)

    inv_b4 = by_no[f"NOR-{tag}-0109"]
    b4 = world.booking(inv_b4.booking_ref)
    row = min(arrival_of_row(world, c) for c in world.containers_of(b4.booking_id))
    candidates = [r for r in runs if b4.act_sailing < r < row]
    assert candidates, f"{batch}: no run between b4's sailing and its terminal report"
    inv_b4.invoice_date = candidates[-1]

    inv_b7 = by_no[f"NOR-{tag}-0123"]
    r7 = next(r for r in runs if r >= inv_b7.invoice_date)
    inv_b7.invoice_date = r7
    for n in world.notices:
        if n.kind == "container_reassign":
            n.notice_date = r7 + timedelta(days=1)

    last = max(i.invoice_date for i in invoices)
    return payment_runs(first, last)


# ---------------------------------------------------------- visible world --
def visible_world(world: World, on: date) -> World:
    """The world as the documents on file at `on` describe it."""
    w = copy.deepcopy(world)
    notices = sorted((n for n in world.notices if n.notice_date <= on),
                     key=lambda n: (n.notice_date, n.notice_id))
    w.notices = notices
    w.circulars = [c for c in world.circulars if c.issued <= on]

    for b in w.bookings:
        b.act_sailing = b.reg_sailing
    for n in notices:
        if n.kind == "sailing_amendment":
            w.booking(n.booking_id).act_sailing = n.new_sailing

    for c in w.containers:
        c.act_booking_id = c.reg_booking_id
    for n in notices:
        if n.kind == "container_reassign":
            w.container(n.container_no).act_booking_id = n.new_booking_id

    for c, final in zip(w.containers, world.containers):
        if arrival_of_row(world, final) > on:
            c.act_gross_kg = final.reg_gross_kg
            c.act_gate_out = c.act_empty_return = None
            continue
        c.act_gross_kg = final.act_gross_kg
        c.act_gate_out = final.act_gate_out if final.act_gate_out and final.act_gate_out <= on else None
        c.act_empty_return = (final.act_empty_return
                              if final.act_empty_return and final.act_empty_return <= on else None)
    return w


def move_snapshots(world: World) -> dict[date, list[dict]]:
    """Every day the terminals' move log changes, the full export as of that day."""
    days = set()
    for c in world.containers:
        days.add(arrival_of_row(world, c))
        for x in (c.act_gate_out, c.act_empty_return):
            if x:
                days.add(x)
    out = {}
    for day in sorted(days):
        rows = []
        for c in sorted(world.containers, key=lambda x: x.container_no):
            if arrival_of_row(world, c) > day:
                continue
            gate = c.act_gate_out if c.act_gate_out and c.act_gate_out <= day else None
            ret = c.act_empty_return if c.act_empty_return and c.act_empty_return <= day else None
            rows.append({"container_no": c.container_no, "terminal": c.terminal,
                         "gate_out_date": gate.isoformat() if gate else "",
                         "empty_return_date": ret.isoformat() if ret else "",
                         "weighbridge_kg": c.act_gross_kg})
        out[day] = rows
    return out
