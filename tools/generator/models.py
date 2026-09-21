"""Data models shared by the world builder, trap registry, renderer and truth writer.

Everything here is dev tooling. It never ships into the task directory; only the
files it *produces* (data + truth) are committed there.
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
    "WRONG_SURCHARGE_PERIOD",
    "CONTRACT_VERSION", 
    "FREE_TIME_MISCOUNT", 
    "BASIS_ERROR", 
    "UNAUTHORIZED_CHARGE",
    "FX_RATE", 
    "DUPLICATE_INVOICE", 
    "UNMATCHED", 
    "CREDIT_NOTE",
]
Status = Literal["APPROVED", "PARTIALLY_DISPUTED", "DISPUTED", "DUPLICATE", "CREDIT_NOTE", "UNMATCHED"]

# Charge codes and the landed-cost category each maps to (policy §7.6).
CHARGE_CATEGORY = {
    "OFR": "ocean_freight",
    "BAF": "surcharges", 
    "EIS": "surcharges", 
    "OWS": "surcharges",
    "DOC": "accessorials", 
    "THC_O": "accessorials", 
    "THC_D": "accessorials", 
    "SEAL": "accessorials",
    "DET": "detention",
}


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
    booked_kg: int          # weight on the booking confirmation
    gross_kg: int           # actual packing-list weight (drives overweight, T12)
    cbm: Decimal
    gate_out: Optional[date]
    empty_return: Optional[date]
    terminal: str           # key into contract.detention.terminals and holidays.json
    lines: list[SalesOrderLine] = field(default_factory=list)


@dataclass
class Booking:
    booking_id: str
    vendor: str             # contract vendor code of the carrier that moves it
    bl_number: str
    pol: str
    pod: str
    sailing: date
    eta: date
    containers: list[Container] = field(default_factory=list)

    @property
    def lane(self) -> str:
        return f"{self.pol}-{self.pod}"


@dataclass
class ContractVersion:
    valid_from: date
    valid_to: date
    lanes: dict[str, dict[str, Decimal]]          # lane -> ctype -> rate
    min_ofr: dict[str, Decimal]                   # ctype -> minimum ocean freight
    index_surcharges: dict[str, dict[str, dict[str, Decimal]]]  # code -> "YYYY-MM" -> ctype -> amount
    accessorials: dict[str, tuple[Basis, dict[str, Decimal] | Decimal]]  # code -> (basis, amount or per-ctype)
    overweight: Optional[tuple[int, dict[str, Decimal]]]        # (threshold_kg, ctype -> amount)
    detention_free_days: int
    detention_tiers: list[tuple[int, Optional[int], dict[str, Decimal]]]  # (from_day, to_day|None, ctype->rate)
    terminal_modes: dict[str, Literal["calendar", "working"]]


@dataclass
class Contract:
    vendor: str
    currency: Literal["USD", "EUR"]
    versions: list[ContractVersion]


@dataclass
class World:
    seed: int
    bookings: list[Booking]
    contracts: dict[str, Contract]
    holidays: dict[str, list[date]]              # terminal -> dates
    fx: dict[date, Decimal]                      # date -> EUR_USD


# -------------------------------------------------------------- invoices ----
@dataclass
class ChargeLine:
    charge_code: str
    description: str
    container_no: Optional[str]
    bl_number: Optional[str]
    amount: Decimal                              # in invoice currency
    # --- truth (hidden) ---
    expected_usd: Decimal = Decimal("0")
    decision: Decision = "APPROVE"
    reason: Reason = "OK"
    trap: Optional[str] = None                   # trap id that produced this line's outcome


@dataclass
class Invoice:
    invoice_number: str
    vendor: str
    layout: str                                  # renderer key
    invoice_date: date
    currency: Literal["USD", "EUR"]
    booking_ref: Optional[str]                   # as printed (may carry a typo, T09)
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
