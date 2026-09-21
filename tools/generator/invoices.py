"""Builds the invoice set for a batch.

Each invoice is billed the way that vendor would bill it — correctly in most
places, and wrongly where a trap says so. Nothing here decides an outcome:
expected amounts, decisions and reasons are derived independently in `truth.py`
from the policy. The only truth this module records is the trap tag on a line,
so the verifier can group its assertions per trap.

Trap ids
--------
T01 sailing amendment cascades into contract version, surcharge month and FX date
T02 rate increase billed before its 30-day notice period has run (over-billed)
T03 tariff circular lowers a surcharge — vendor bills the stale contract amount (over-billed)
T04 detention billed on register dates in calendar mode at a working-day terminal
T05 per-B/L documentation fee billed once per container on a consolidation
T06 container rolled to another booking after the ERP export
T07 overweight surcharge justified by the weighbridge weight (legitimate)
T08 ocean freight at the contract minimum (legitimate)
T09 charge code absent from the contract
T10 duplicate invoice re-issued under a new number
T11 credit note against an over-billed line
T12 invoice that matches no booking in the register
T13 EUR invoice converted at the sailing-date fixing (legitimate)
T14 rate increase correctly in force once its 30-day notice period has run (legitimate)
T15 (hidden batch only) overweight billed on register weight; weighbridge is below threshold
T16 (hidden batch only) per-shipment fee billed once per container
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pricing
from models import ChargeLine, Invoice, World
from world import VENDORS, BatchSpec

D = Decimal

DESCRIPTIONS = {
    "OFR": "Ocean freight",
    "BAF": "Bunker adjustment factor",
    "THC_O": "Terminal handling - origin",
    "THC_D": "Terminal handling - destination",
    "SEAL": "Container seal",
    "DOC": "Documentation fee",
    "DET": "Detention",
    "OWS": "Overweight surcharge",
    "CGS": "Port congestion surcharge",
    "ISPS": "Port security surcharge",
}


def _line(code, container, bl, amount, trap=None) -> ChargeLine:
    return ChargeLine(
        charge_code=code,
        description=DESCRIPTIONS[code],
        container_no=container,
        bl_number=bl,
        amount=pricing.q(amount),
        trap=trap,
    )


def _inv(s: BatchSpec, vendor: str, n: int, month_off: int, day: int, booking_ref, bl_ref,
         lines, **kw) -> Invoice:
    return Invoice(
        invoice_number=f"{vendor[:3]}-{s.batch.upper()}-{n:04d}",
        vendor=vendor,
        layout=VENDORS[vendor]["layout"],
        invoice_date=s.d(month_off, day),
        currency=VENDORS[vendor]["currency"],
        booking_ref=booking_ref,
        bl_ref=bl_ref,
        lines=lines,
        **kw,
    )


def build_invoices(world: World, s: BatchSpec) -> list[Invoice]:
    out: list[Invoice] = []
    b = {bk.booking_id: bk for bk in world.bookings}
    ids = [f"BK{s.n(i)}" for i in range(1, 8)]
    b1, b2, b3, b4, b5, b6, b7 = (b[i] for i in ids)

    def containers(booking, *, actual=True):
        return world.containers_of(booking.booking_id, actual=actual)

    def carrier_lines(booking, *, on=None, trap=None, skip=()):
        """OFR + BAF + THC_O + SEAL for every container of the booking, priced at
        `on` (defaults to the controlling sailing date)."""
        sail = on or booking.act_sailing
        lines = []
        for c in containers(booking):
            if "OFR" not in skip:
                lines.append(_line("OFR", c.container_no, booking.bl_number,
                                   pricing.ocean_freight(world, booking, c.ctype, on=sail,
                                                         vendor_view=True), trap))
            if "BAF" not in skip:
                baf = pricing.index_surcharge(world, booking, "BAF", c.ctype, on=sail, vendor_view=True)
                lines.append(_line("BAF", c.container_no, booking.bl_number, baf, trap))
            if "THC_O" not in skip:
                basis, amt = pricing.accessorial(world, booking.vendor, "THC_O", c.ctype,
                                                 booking.lane, sail, vendor_view=True)
                lines.append(_line("THC_O", c.container_no, booking.bl_number, amt))
            if "SEAL" not in skip:
                _, amt = pricing.accessorial(world, booking.vendor, "SEAL", c.ctype,
                                             booking.lane, sail)
                lines.append(_line("SEAL", c.container_no, booking.bl_number, amt))
        return lines

    def doc_line(booking, on=None):
        sail = on or booking.act_sailing
        _, amt = pricing.accessorial(world, booking.vendor, "DOC", "20DV", booking.lane, sail)
        return _line("DOC", None, booking.bl_number, amt)

    # ---- INV 1: b1. Minimum ocean freight (T08) + unauthorised congestion (T09)
    lines = carrier_lines(b1)
    for l in lines:
        if l.charge_code == "OFR":
            l.trap = "T08"
    lines.append(_line("CGS", containers(b1)[0].container_no, b1.bl_number, D("180"), "T09"))
    if s.batch == "b":
        # Hidden batch only. (T15) Overweight billed on the register weight,
        # which the weighbridge contradicts. (T16) The per-shipment ISPS fee
        # billed once per container: only the first line is due.
        for c in containers(b1):
            ows = pricing.overweight(world, b1, c, use_register=True)
            if ows > 0:
                lines.append(_line("OWS", c.container_no, b1.bl_number, ows, "T15"))
        for i, c in enumerate(containers(b1)):
            _, isps = pricing.accessorial(world, b1.vendor, "ISPS", c.ctype, b1.lane, b1.act_sailing)
            lines.append(_line("ISPS", c.container_no, b1.bl_number, isps, "T16" if i else None))
    lines.append(doc_line(b1))
    inv1 = _inv(s, "NORDVIK", 101, 0, 27, b1.booking_id, b1.bl_number, lines)
    out.append(inv1)

    # ---- INV 2: duplicate of INV 1, re-issued weeks later (T10) -------------
    dup_lines = [_line(l.charge_code, l.container_no, l.bl_number, l.amount, "T10") for l in lines]
    out.append(_inv(s, "NORDVIK", 118, 1, 14, b1.booking_id, b1.bl_number, dup_lines))

    # ---- INV 3: b2 billed against the SUPERSEDED sailing date (T01) ---------
    # The carrier invoiced from its own booking record, which still carries the
    # pre-amendment sailing: old contract version and the previous BAF month.
    lines = carrier_lines(b2, on=b2.reg_sailing, trap="T01")
    lines.append(doc_line(b2))
    out.append(_inv(s, "NORDVIK", 104, 1, 8, b2.booking_id, b2.bl_number, lines))

    # ---- INV 4: b3 EUR invoice, detention on register dates (T04, T13) ------
    lines = carrier_lines(b3)
    for l in lines:
        if l.charge_code == "OFR":
            l.trap = "T13"
    for c in containers(b3):
        wrong = pricing.detention(world, b3, c, use_register_dates=True, force_mode="calendar")
        if wrong > 0:
            lines.append(_line("DET", c.container_no, b3.bl_number, wrong, "T04"))
    lines.append(doc_line(b3))
    out.append(_inv(s, "ATLASOCEAN", 106, 1, 26, b3.booking_id, b3.bl_number, lines))

    # ---- INV 5: b4 stale THC_O despite the circular (T02) + overweight (T07) -
    lines = carrier_lines(b4)
    for l in lines:
        if l.charge_code == "THC_O":
            l.trap = "T02"   # increase billed before the 30-day notice period ran
    for c in containers(b4):
        ows = pricing.overweight(world, b4, c)
        if ows > 0:
            lines.append(_line("OWS", c.container_no, b4.bl_number, ows, "T07"))
    lines.append(doc_line(b4))
    out.append(_inv(s, "NORDVIK", 109, 1, 30, b4.booking_id, b4.bl_number, lines))

    # ---- INV 6: b5 EUR, BAF billed from the superseded tariff row (T03) -----
    lines = carrier_lines(b5, skip=("BAF",))
    v5 = pricing.version_for(world, b5.vendor, b5.act_sailing)
    row = v5.index_surcharges["BAF"][f"{b5.act_sailing.year}-{b5.act_sailing.month:02d}"]
    for c in containers(b5):
        lines.append(_line("BAF", c.container_no, b5.bl_number, row[c.ctype], "T03"))
    lines.append(doc_line(b5))
    inv6 = _inv(s, "ATLASOCEAN", 112, 2, 3, b5.booking_id, b5.bl_number, lines)
    out.append(inv6)

    # ---- INV 7: credit note correcting one BAF line of INV 6 (T11) ----------
    c0 = containers(b5)[0]
    correct = pricing.index_surcharge(world, b5, "BAF", c0.ctype)
    delta = row[c0.ctype] - correct
    out.append(
        _inv(
            s, "ATLASOCEAN", 115, 2, 17, b5.booking_id, b5.bl_number,
            [_line("BAF", c0.container_no, b5.bl_number, -delta, "T11")],
            is_credit_note=True,
            credit_for=inv6.invoice_number,
        )
    )

    # ---- INV 8/9: b6 and b7, with one container rolled between them (T06) ---
    for bk, num, day in ((b6, 120, 6), (b7, 123, 12)):
        lines = carrier_lines(bk)
        for l in lines:
            c = world.container(l.container_no)
            if c.reassigned:
                l.trap = "T06"
            elif l.charge_code == "THC_O":
                # b6 sails before the notice period ends (billed anyway: T02);
                # b7 sails after it, so the increase is correctly in force (T14).
                l.trap = "T02" if bk is b6 else "T14"
        lines.append(doc_line(bk))
        out.append(_inv(s, "NORDVIK", num, 2, day, bk.booking_id, bk.bl_number, lines))

    # ---- INV 10: forwarder consolidation, DOC billed per container (T05) ----
    lines = []
    for bk in (b4, b5):
        for c in containers(bk):
            _, thc = pricing.accessorial(world, "HARBORLINK", "THC_D", c.ctype, bk.lane,
                                         bk.act_sailing)
            lines.append(_line("THC_D", c.container_no, bk.bl_number, thc))
        for i, c in enumerate(containers(bk)):
            _, doc = pricing.accessorial(world, "HARBORLINK", "DOC", c.ctype, bk.lane,
                                         bk.act_sailing)
            lines.append(_line("DOC", c.container_no, bk.bl_number, doc, "T05" if i else None))
    out.append(_inv(s, "HARBORLINK", 130, 2, 20, None, None, lines))

    # ---- INV 11: forwarder invoice for a shipment we never booked (T12) -----
    ghost = [f"HLXU{s.n(9)}{j}00" for j in (1, 2)]
    lines = [_line("THC_D", g, f"HLK{s.n(9)}BL", D("315"), "T12") for g in ghost]
    lines.append(_line("DOC", None, f"HLK{s.n(9)}BL", D("110"), "T12"))
    out.append(_inv(s, "HARBORLINK", 133, 2, 24, f"BK{s.n(9)}", f"HLK{s.n(9)}BL", lines))

    out.sort(key=lambda i: i.invoice_number)
    return out
