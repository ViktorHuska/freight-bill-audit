"""Data models shared by the world builder, trap registry, renderer and truth writer.

Everything here is dev tooling. It never ships into the task directory; only the
files it *produces* (data + truth) are committed there.

The central idea of the task lives in this module: several objects carry both a
*register* value and an *actual* value. The register is what the ERP export
(`shipments.json`) says; the actual is what the controlling source in policy §2
says (a terminal move log, or a later carrier notice). A tool that reads only
the register gets a self-consistent but wrong answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

Basis = Literal["per_container", "per_bl", "per_shipment"]
Decision = Literal["APPROVE", "DISPUTE"]
Reason = Literal[
    "OK",
    "WITHIN_TOLERANCE",
    "UNDERBILLED",
    "RATE_MISMATCH",
    "BASIS_ERROR",
    "UNAUTHORIZED_CHARGE",
    "FREE_TIME_MISCOUNT",
    "DUPLICATE_INVOICE",
    "UNMATCHED",
    "CREDIT_NOTE",
]
Status = Literal["APPROVED", "PARTIALLY_DISPUTED", "DISPUTED", "DUPLICATE", "CREDIT_NOTE", "UNMATCHED"]

# Charge code -> landed-cost category (policy §7.6). Anything not listed here is
# an accessorial; UNAUTHORIZED codes never allocate because they price to 0.00.
CHARGE_CATEGORY = {
    "OFR": "ocean_freight",
    "BAF": "surcharges",
    "EIS": "surcharges",
    "OWS": "surcharges",
    "DET": "detention",
}
DEFAULT_CATEGORY = "accessorials"


def category_of(code: str) -> str:
    return CHARGE_CATEGORY.get(code, DEFAULT_CATEGORY)


# ---------------------------------------------------------------- world ----
@dataclass
class SalesOrderLine:
    so: str
    gross_kg: int
    cbm: Decimal
    value_usd: Decimal


@dataclass
class Container:
    container_no: str
    ctype: Literal["20DV", "40HC"]
    booked_kg: int
    cbm: Decimal
    terminal: str
    lines: list[SalesOrderLine] = field(default_factory=list)

    # --- register view (shipments.json) ---
    reg_booking_id: str = ""
    reg_gross_kg: int = 0
    reg_gate_out: Optional[date] = None
    reg_empty_return: Optional[date] = None

    # --- controlling view (terminal_moves.csv / notices) ---
    act_booking_id: str = ""
    act_gross_kg: int = 0
    act_gate_out: Optional[date] = None
    act_empty_return: Optional[date] = None
    # A container only appears in terminal_moves.csv once it has been returned.
    in_move_log: bool = True

    @property
    def reassigned(self) -> bool:
        return self.act_booking_id != self.reg_booking_id


@dataclass
class Booking:
    booking_id: str
    vendor: str
    bl_number: str
    pol: str
    pod: str
    eta: date
    reg_sailing: date
    act_sailing: date

    @property
    def lane(self) -> str:
        return f"{self.pol}-{self.pod}"

    @property
    def amended(self) -> bool:
        return self.act_sailing != self.reg_sailing


@dataclass
class Terminal:
    code: str
    weekend: list[str]          # e.g. ["Fri", "Sat"] — policy §3.7
    closures: list[date]


@dataclass
class ContractVersion:
    valid_from: date
    valid_to: date
    lanes: dict[str, dict[str, Decimal]]                        # lane -> ctype -> rate
    min_ofr: dict[str, Decimal]                                 # ctype -> minimum
    index_surcharges: dict[str, dict[str, dict[str, Decimal]]]  # code -> "YYYY-MM" -> ctype -> amt
    accessorials: dict[str, tuple[Basis, Decimal | dict[str, Decimal]]]
    overweight: Optional[tuple[int, dict[str, Decimal]]]        # (threshold_kg, ctype -> amt)
    detention_free_days: int
    detention_tiers: list[tuple[int, Optional[int], dict[str, Decimal]]]
    terminal_modes: dict[str, Literal["calendar", "working"]]


@dataclass
class Contract:
    vendor: str
    currency: Literal["USD", "EUR"]
    versions: list[ContractVersion]


@dataclass
class Revision:
    """One line of a tariff circular (policy §3.2)."""
    charge_code: str
    lane: Optional[str]                     # None = all lanes
    amount: Decimal | dict[str, Decimal]    # flat, or per container type


@dataclass
class Circular:
    circular_id: str
    vendor: str
    issued: date
    effective_from: date
    revisions: list[Revision]
    subject: str


@dataclass
class Notice:
    """Carrier/forwarder correspondence written to notices/*.txt."""
    notice_id: str
    vendor: str
    notice_date: date
    kind: Literal["sailing_amendment", "container_reassign", "credit_advice", "circular", "noise"]
    subject: str
    body: str
    # Structured payload the renderer turns into prose; also used by truth.
    booking_id: Optional[str] = None
    container_no: Optional[str] = None
    new_sailing: Optional[date] = None
    new_booking_id: Optional[str] = None
    circular_id: Optional[str] = None
    prev_sailing: Optional[date] = None      # "previously ..." when not the register date


@dataclass
class World:
    seed: int
    bookings: list[Booking]
    containers: list[Container]
    contracts: dict[str, Contract]
    circulars: list[Circular]
    notices: list[Notice]
    terminals: dict[str, Terminal]
    fx: dict[date, Decimal]
    # ERP keying mistakes: the contracts/*.json the ERP holds differ from the
    # signed agreement at these points. (vendor, version index or None for all
    # versions, section, key, container type or None, value keyed in).
    keying_errors: list[tuple] = field(default_factory=list)

    def booking(self, booking_id: str) -> Booking:
        for b in self.bookings:
            if b.booking_id == booking_id:
                return b
        raise KeyError(booking_id)

    def container(self, container_no: str) -> Container:
        for c in self.containers:
            if c.container_no == container_no:
                return c
        raise KeyError(container_no)

    def containers_of(self, booking_id: str, *, actual: bool = True) -> list[Container]:
        key = "act_booking_id" if actual else "reg_booking_id"
        return [c for c in self.containers if getattr(c, key) == booking_id]


# -------------------------------------------------------------- invoices ----
@dataclass
class ChargeLine:
    charge_code: str
    description: str
    container_no: Optional[str]
    bl_number: Optional[str]
    amount: Decimal                              # in invoice currency, as printed
    # --- truth (hidden) ---
    expected_usd: Decimal = Decimal("0")
    decision: Decision = "APPROVE"
    reason: Reason = "OK"
    trap: Optional[str] = None


@dataclass
class Invoice:
    invoice_number: str
    vendor: str
    layout: str
    invoice_date: date
    currency: Literal["USD", "EUR"]
    booking_ref: Optional[str]
    bl_ref: Optional[str]
    lines: list[ChargeLine] = field(default_factory=list)
    is_credit_note: bool = False
    credit_for: Optional[str] = None
    # --- truth (hidden) ---
    status: Status = "APPROVED"
    duplicate_of: Optional[str] = None
    matched_bookings: list[str] = field(default_factory=list)
    traps: list[str] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((l.amount for l in self.lines), Decimal("0"))
