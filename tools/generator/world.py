"""Deterministic world builder.

Both batches share vendors, layouts, lanes, terminals and contract *families*;
they differ in period, ids, rates, index rows and where each trap is planted.
The world is written out explicitly rather than sampled, so every precondition
the trap registry needs is guaranteed by construction and a batch is
reproducible byte for byte.

Naming: `reg_*` is what the ERP export claims, `act_*` is what the controlling
source in policy §2 says. Where they differ, a notice or the terminal move log
carries the correction and the register is left stale on purpose.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from models import (
    Booking,
    Circular,
    Container,
    Contract,
    ContractVersion,
    Notice,
    Revision,
    SalesOrderLine,
    Terminal,
    World,
)

D = Decimal

VENDORS = {
    "NORDVIK": dict(kind="carrier", currency="USD", layout="table", prefix="NVKU"),
    "ATLASOCEAN": dict(kind="carrier", currency="EUR", layout="lines", prefix="ATLU"),
    "HARBORLINK": dict(kind="forwarder", currency="USD", layout="consolidated", prefix=None),
}

LANES = ["USSAV-AEJEA", "USHOU-AEJEA", "USSAV-SAJED", "USHOU-PKQCT"]

# Weekends are per terminal and are NOT Mon-Fri everywhere: Jeddah runs a
# Friday/Saturday weekend, Karachi a single Sunday. policy §3.7 points at
# holidays.json for this; a tool that hardcodes Mon-Fri miscounts detention.
TERMINAL_SPEC = {
    "AEJEA-T1": dict(weekend=["Sat", "Sun"], mode="calendar"),
    "AEJEA-T2": dict(weekend=["Sat", "Sun"], mode="working"),
    "SAJED-KCT": dict(weekend=["Fri", "Sat"], mode="working"),
    "PKQCT-QICT": dict(weekend=["Sun"], mode="calendar"),
}


class BatchSpec:
    """Everything that differs between batch A and batch B."""

    # batch -> (year, first month, id sequence base, 40HC rate shift, closure offset)
    # a, b: the audited batches (visible, hidden). h1, h2: two settled months of
    # history that ship with the AP ledger, so every legacy-tool defect is
    # observable in what was actually paid.
    PARAMS = {
        "a": (2024, 2, 2400, "0", 0),
        "b": (2024, 8, 2490, "60", 1),
        "h1": (2023, 9, 2310, "30", 2),
        "h2": (2023, 12, 2350, "-30", 0),
    }

    def __init__(self, batch: str):
        self.batch = batch
        year, m0, seq, shift, closure = self.PARAMS[batch]
        self.year = year
        self.m0 = m0                         # contract v1 month
        self.seq = seq
        self.rate_shift = D(shift)           # different money, same structure
        self.closure_offset = closure

    def d(self, month_offset: int, day: int) -> date:
        """A date `month_offset` months after the batch's first month."""
        m = self.m0 + month_offset
        y = self.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        return date(y, m, day)

    def n(self, i: int) -> str:
        return f"{self.seq + i}"


def _contract_nordvik(s: BatchSpec) -> Contract:
    shift = s.rate_shift
    v1_lanes = {
        "USSAV-AEJEA": {"20DV": D("1850"), "40HC": D("2900") + shift},
        "USHOU-AEJEA": {"20DV": D("1920"), "40HC": D("3010") + shift},
        "USSAV-SAJED": {"20DV": D("2050"), "40HC": D("3260") + shift},
    }
    # The renewal is not uniformly up: USHOU-AEJEA softened at renewal, so an
    # invoice priced against the superseded version OVER-bills that lane while
    # the other lanes went up. A tool that ignores the amendment gets the sign
    # of the error wrong as well as the amount.
    v2_lanes = {
        "USSAV-AEJEA": {"20DV": D("1990"), "40HC": D("3120") + shift},
        "USHOU-AEJEA": {"20DV": D("1780"), "40HC": D("2850") + shift},
        "USSAV-SAJED": {"20DV": D("2180"), "40HC": D("3390") + shift},
    }
    # Minimum sits ABOVE the v1 40HC lane rate on USSAV-AEJEA: billing the
    # minimum there is correct and must not be disputed (policy §3.4).
    min_ofr = {"20DV": D("0"), "40HC": D("3050") + shift}

    # The index falls between the first and second month, so pricing a sailing
    # from the wrong month over-bills rather than under-bills.
    baf = {}
    for off, (dv, hc) in enumerate([("352", "705"), ("298", "596"), ("310", "620")]):
        key = f"{s.d(off, 1).year}-{s.d(off, 1).month:02d}"
        baf[key] = {"20DV": D(dv), "40HC": D(hc)}

    accessorials = {
        "DOC": ("per_bl", D("95")),
        "THC_O": ("per_container", {"20DV": D("260"), "40HC": D("340")}),
        "SEAL": ("per_container", D("18")),
        "DET": ("per_container", D("0")),  # priced by the detention schedule
    }
    tiers = [
        (1, 7, {"20DV": D("75"), "40HC": D("110")}),
        (8, None, {"20DV": D("130"), "40HC": D("190")}),
    ]
    common = dict(
        min_ofr=min_ofr,
        index_surcharges={"BAF": baf},
        accessorials=accessorials,
        overweight=(20000, {"20DV": D("120"), "40HC": D("150")}),
        detention_free_days=7,
        detention_tiers=tiers,
        terminal_modes={k: v["mode"] for k, v in TERMINAL_SPEC.items()},
    )
    v1 = ContractVersion(valid_from=s.d(-1, 1), valid_to=s.d(0, 29), lanes=v1_lanes, **common)
    v2 = ContractVersion(valid_from=s.d(1, 1), valid_to=s.d(4, 28), lanes=v2_lanes, **common)
    return Contract(vendor="NORDVIK", currency="USD", versions=[v1, v2])


def _contract_atlasocean(s: BatchSpec) -> Contract:
    shift = s.rate_shift
    lanes = {
        "USSAV-SAJED": {"20DV": D("1760"), "40HC": D("2810") + shift},
        "USHOU-PKQCT": {"20DV": D("1690"), "40HC": D("2740") + shift},
    }
    baf = {}
    for off, (dv, hc) in enumerate([("268", "536"), ("291", "582"), ("254", "508")]):
        key = f"{s.d(off, 1).year}-{s.d(off, 1).month:02d}"
        baf[key] = {"20DV": D(dv), "40HC": D(hc)}
    accessorials = {
        "DOC": ("per_bl", D("80")),
        "THC_O": ("per_container", {"20DV": D("225"), "40HC": D("295")}),
        "SEAL": ("per_container", D("15")),
        "DET": ("per_container", D("0")),
    }
    tiers = [
        (1, 5, {"20DV": D("62"), "40HC": D("94")}),
        (6, None, {"20DV": D("115"), "40HC": D("168")}),
    ]
    common = dict(
        min_ofr={"20DV": D("0"), "40HC": D("0")},
        index_surcharges={"BAF": baf},
        accessorials=accessorials,
        overweight=(20000, {"20DV": D("105"), "40HC": D("140")}),
        detention_free_days=5,
        detention_tiers=tiers,
        terminal_modes={k: v["mode"] for k, v in TERMINAL_SPEC.items()},
    )
    # One contract version only: ATLASOCEAN's rate agreement spans the period.
    v1 = ContractVersion(valid_from=s.d(-1, 1), valid_to=s.d(4, 28), lanes=lanes, **common)
    return Contract(vendor="ATLASOCEAN", currency="EUR", versions=[v1])


def _contract_harborlink(s: BatchSpec) -> Contract:
    accessorials = {
        "THC_D": ("per_container", {"20DV": D("240"), "40HC": D("315")}),
        "DOC": ("per_bl", D("110")),
    }
    v1 = ContractVersion(
        valid_from=s.d(-1, 1),
        valid_to=s.d(4, 28),
        lanes={},
        min_ofr={},
        index_surcharges={},
        accessorials=accessorials,
        overweight=None,
        detention_free_days=0,
        detention_tiers=[],
        terminal_modes={k: v["mode"] for k, v in TERMINAL_SPEC.items()},
    )
    return Contract(vendor="HARBORLINK", currency="USD", versions=[v1])


def _fx(s: BatchSpec) -> dict[date, Decimal]:
    """Business-day EUR/USD fixings across the batch period. Weekends are absent
    on purpose so policy §3.9's fallback rule has to be implemented."""
    out: dict[date, Decimal] = {}
    day = s.d(-1, 1)
    end = s.d(4, 28)
    rate = D("1.0820")
    step = D("0.0013")
    i = 0
    while day <= end:
        if day.weekday() < 5:
            # Deterministic zig-zag: enough movement that the wrong date is
            # visible in cents on a four-figure invoice.
            rate = rate + step if (i // 3) % 2 == 0 else rate - step
            out[day] = rate.quantize(D("0.0001"))
            i += 1
        day += timedelta(days=1)
    return out


def _sales_orders(s: BatchSpec, idx: int, n: int, total_kg: int) -> list[SalesOrderLine]:
    """`n` sales-order lines splitting `total_kg` unevenly, so weight-proportional
    allocation produces remainders that the largest-remainder rule must settle."""
    out = []
    weights = [37, 29, 21, 13][:n]
    scale = sum(weights)
    for j, w in enumerate(weights):
        kg = total_kg * w // scale
        out.append(
            SalesOrderLine(
                so=f"SO-{s.n(idx * 4 + j)}",
                gross_kg=kg,
                cbm=D(kg) / D("180"),
                value_usd=D(kg) * D("4.25"),
            )
        )
    return out


def build_world(batch: str) -> World:
    s = BatchSpec(batch)
    terminals = {
        code: Terminal(
            code=code,
            weekend=spec["weekend"],
            closures=[
                s.d(1, 10 + s.closure_offset),
                s.d(1, 11 + s.closure_offset),
                s.d(2, 4 + s.closure_offset),
            ],
        )
        for code, spec in TERMINAL_SPEC.items()
    }

    contracts = {
        "NORDVIK": _contract_nordvik(s),
        "ATLASOCEAN": _contract_atlasocean(s),
        "HARBORLINK": _contract_harborlink(s),
    }

    bookings: list[Booking] = []
    containers: list[Container] = []
    notices: list[Notice] = []
    circulars: list[Circular] = []

    def add_booking(i, vendor, lane, sail_off, sail_day, *, act_sail=None) -> Booking:
        pol, pod = lane.split("-")
        reg_sailing = s.d(sail_off, sail_day)
        b = Booking(
            booking_id=f"BK{s.n(i)}",
            vendor=vendor,
            bl_number=f"{vendor[:3]}{s.n(i)}BL",
            pol=pol,
            pod=pod,
            eta=reg_sailing + timedelta(days=21),
            reg_sailing=reg_sailing,
            act_sailing=act_sail or reg_sailing,
        )
        bookings.append(b)
        return b

    def add_container(i, j, booking, ctype, terminal, *, kg, weigh_kg=None,
                      gate_off=None, return_off=None, reg_gate_shift=0, act_booking=None,
                      in_log=True) -> Container:
        c = Container(
            container_no=f"{VENDORS[booking.vendor]['prefix'] or 'HLXU'}{s.n(i)}{j}00",
            ctype=ctype,
            booked_kg=kg - 900,
            cbm=D("58") if ctype == "40HC" else D("31"),
            terminal=terminal,
            lines=_sales_orders(s, i * 3 + j, 3 if ctype == "40HC" else 2, kg),
            reg_booking_id=booking.booking_id,
            act_booking_id=(act_booking or booking).booking_id,
            reg_gross_kg=kg,
            act_gross_kg=weigh_kg if weigh_kg is not None else kg,
            in_move_log=in_log,
        )
        if gate_off is not None:
            act_gate = booking.eta + timedelta(days=gate_off)
            c.act_gate_out = act_gate
            c.act_empty_return = act_gate + timedelta(days=return_off)
            # The register carries the *planned* dates, keyed in at booking time.
            c.reg_gate_out = act_gate - timedelta(days=reg_gate_shift)
            c.reg_empty_return = c.act_empty_return - timedelta(days=reg_gate_shift)
        containers.append(c)
        return c

    # -- b1: v1 rates, 40HC lane below the contract minimum (legitimate) ------
    b1 = add_booking(1, "NORDVIK", "USSAV-AEJEA", 0, 20)
    add_container(1, 1, b1, "40HC", "AEJEA-T1", kg=18400)
    add_container(1, 2, b1, "40HC", "AEJEA-T1", kg=17250)

    # -- b2: sailing amended across BOTH the month and the version boundary ---
    b2 = add_booking(2, "NORDVIK", "USHOU-AEJEA", 0, 26, act_sail=s.d(1, 4))
    # Both 20DV: the 40HC minimum floor would otherwise mask the version change
    # behind an identical floored rate and the trap would price to no variance.
    add_container(2, 1, b2, "20DV", "AEJEA-T2", kg=16100)
    add_container(2, 2, b2, "20DV", "AEJEA-T2", kg=15350)
    notices.append(
        Notice(
            notice_id=f"N{s.n(2)}-01",
            vendor="NORDVIK",
            notice_date=s.d(0, 24),
            kind="sailing_amendment",
            subject=f"Vessel change / revised sailing — booking BK{s.n(2)}",
            body="",
            booking_id=b2.booking_id,
            new_sailing=s.d(1, 4),
        )
    )

    # -- b3: detention at a Fri/Sat-weekend terminal, actual dates in the log --
    b3 = add_booking(3, "ATLASOCEAN", "USSAV-SAJED", 1, 6)
    add_container(3, 1, b3, "20DV", "SAJED-KCT", kg=15800, gate_off=2, return_off=16, reg_gate_shift=3)
    add_container(3, 2, b3, "20DV", "SAJED-KCT", kg=14900, gate_off=2, return_off=11, reg_gate_shift=3)

    # -- b4: tariff circular raises THC_O; weighbridge trips overweight --------
    b4 = add_booking(4, "NORDVIK", "USSAV-AEJEA", 1, 12)
    add_container(4, 1, b4, "40HC", "AEJEA-T2", kg=19200, weigh_kg=21400)
    add_container(4, 2, b4, "20DV", "AEJEA-T2", kg=15400)
    circ_up = Circular(
        circular_id=f"NVK-TAR-{s.n(4)}",
        vendor="NORDVIK",
        issued=s.d(1, 5),
        effective_from=s.d(1, 10),
        revisions=[
            Revision("THC_O", "USSAV-AEJEA", {"20DV": D("285"), "40HC": D("370")}),
        ],
        subject="Revised origin terminal handling — US South Atlantic",
    )
    circulars.append(circ_up)

    # -- b5: circular lowers BAF; vendor keeps billing the contract row -------
    b5 = add_booking(5, "ATLASOCEAN", "USHOU-PKQCT", 1, 18)
    add_container(5, 1, b5, "40HC", "PKQCT-QICT", kg=18700)
    add_container(5, 2, b5, "40HC", "PKQCT-QICT", kg=19600)
    circ_down = Circular(
        circular_id=f"ATL-TAR-{s.n(5)}",
        vendor="ATLASOCEAN",
        issued=s.d(1, 13),
        effective_from=s.d(1, 15),
        revisions=[Revision("BAF", "USHOU-PKQCT", {"20DV": D("236"), "40HC": D("472")})],
        subject="Bunker adjustment — Pakistan service, revised",
    )
    circulars.append(circ_down)

    # -- b6 / b7: a container rolled to the next vessel after the ERP export ---
    b6 = add_booking(6, "NORDVIK", "USSAV-SAJED", 1, 22)
    # The receiving vessel sails in the NEXT month, so the roll moves the rolled
    # container's BAF row. Without that, ignoring the roll would price
    # identically, and no paid total could ever reveal that rolls matter.
    b7 = add_booking(7, "NORDVIK", "USSAV-SAJED", 2, 3)
    add_container(6, 1, b6, "20DV", "SAJED-KCT", kg=15200)
    rolled = add_container(6, 2, b6, "20DV", "SAJED-KCT", kg=16400, act_booking=b7)
    add_container(7, 1, b7, "40HC", "SAJED-KCT", kg=18900)
    notices.append(
        Notice(
            notice_id=f"N{s.n(6)}-02",
            vendor="NORDVIK",
            notice_date=s.d(1, 21),
            kind="container_reassign",
            subject=f"Roll advice — container {rolled.container_no}",
            body="",
            container_no=rolled.container_no,
            booking_id=b6.booking_id,
            new_booking_id=b7.booking_id,
        )
    )

    # -- noise: correspondence that changes nothing --------------------------
    notices.append(
        Notice(
            notice_id=f"N{s.n(1)}-03",
            vendor="HARBORLINK",
            notice_date=s.d(1, 8),
            kind="noise",
            subject="Office relocation and remittance details",
            body="",
        )
    )

    return World(
        seed=s.seq,
        bookings=bookings,
        containers=containers,
        contracts=contracts,
        circulars=circulars,
        notices=notices,
        terminals=terminals,
        fx=_fx(s),
    )
