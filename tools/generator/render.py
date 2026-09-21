"""Vendor PDF layouts (reportlab). Text-based PDFs only — no OCR anywhere.

Three layouts, one per vendor, different enough that a single regex does not
work across all of them:

  table        NORDVIK    ruled columns: code | description | container | amount
  lines        ATLASOCEAN free-text charge lines, EUR, European number format
  consolidated HARBORLINK statement grouped by B/L with per-B/L subtotals

Every writer prints the invoice number, date, vendor, currency and the booking
and B/L references exactly as stored on the Invoice, prints the lines in order,
and prints a total equal to Invoice.total. Credit notes are titled CREDIT NOTE
and carry the corrected invoice's number.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfgen import canvas as rl_canvas

from models import Invoice

LEFT = 54


def _us(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _eu(amount: Decimal) -> str:
    """1234.5 -> 1.234,50 (and -1234.5 -> -1.234,50)."""
    s = f"{abs(amount):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("-" if amount < 0 else "") + s


def _title(inv: Invoice) -> str:
    return "CREDIT NOTE" if inv.is_credit_note else "INVOICE"


BASIS_TEXT = {"per_container": "per container", "per_bl": "per bill of lading",
              "per_shipment": "per shipment"}
CARRIER_NAME = {"NORDVIK": "NORDVIK LINE", "ATLASOCEAN": "ATLAS OCEAN NV",
                "HARBORLINK": "HARBORLINK LOGISTICS"}
CODE_TEXT = {"DOC": "Documentation", "THC_O": "Terminal handling, origin",
             "THC_D": "Terminal handling, destination", "SEAL": "Container seal",
             "DET": "Detention", "ISPS": "Port security"}


def _amts(amount) -> str:
    if isinstance(amount, dict):
        return "  ".join(f"{t} {_us(a)}" for t, a in sorted(amount.items()))
    return _us(amount)


def agreement_lines(world, vendor: str, agreement_no: str) -> list[str]:
    """Text of the signed agreement, from the AGREED (true) contract values."""
    c = world.contracts[vendor]
    L = [
        "RATE AGREEMENT",
        f"Agreement no. {agreement_no}",
        f"Between: International Sales Office (Shipper) and {CARRIER_NAME[vendor]} ({vendor})",
        f"Currency of all amounts: {c.currency}",
        "",
        "Clause 1 - Precedence. This agreement and its amendments govern every charge billed",
        "to the Shipper. It prevails over any tariff, rate sheet or system record derived from it.",
        "Clause 2 - Notice. For shipments in the United States trades, an increase in any rate or",
        "charge agreed here, including by tariff circular, takes effect no earlier than 30 days",
        "after the carrier publishes it. A decrease takes effect on the date the carrier states.",
        "Clause 3 - Schedules. Each amendment below applies to shipments whose vessel departs",
        "within its validity window.",
        "",
    ]
    for n, v in enumerate(c.versions, 1):
        L += [f"SCHEDULE A - AMENDMENT {n} - valid {v.valid_from.isoformat()} through {v.valid_to.isoformat()}"]
        if v.lanes:
            L += ["A.1 Ocean freight per container"]
            L += [f"  {lane}  {_amts(rates)}" for lane, rates in sorted(v.lanes.items())]
            L += [f"A.2 Minimum ocean freight per container  {_amts(v.min_ofr)}"]
        for code, table in sorted(v.index_surcharges.items()):
            L += [f"A.3 {code} by calendar month of vessel departure"]
            L += [f"  {month}  {_amts(row)}" for month, row in sorted(table.items())]
        L += ["A.4 Accessorial charges"]
        for code, (basis, amount) in sorted(v.accessorials.items()):
            if code == "DET":
                L += [f"  {code}  {CODE_TEXT[code]}, {BASIS_TEXT[basis]} per day, see A.6"]
            else:
                L += [f"  {code}  {CODE_TEXT.get(code, code)}, {BASIS_TEXT[basis]}  {_amts(amount)}"]
        if v.overweight:
            threshold, amounts = v.overweight
            L += [f"A.5 OWS Overweight surcharge above {threshold:,} kg gross  {_amts(amounts)}"]
        if v.detention_tiers:
            L += [f"A.6 Detention free days {v.detention_free_days}"]
            for lo, hi, rates in v.detention_tiers:
                span = f"days {lo}-{hi}" if hi is not None else f"days {lo}+"
                L += [f"  {span}  {_amts(rates)}"]
            L += ["  Free days and chargeable days are counted in the terminal's mode:"]
            L += [f"  {t}  {m} days" for t, m in sorted(v.terminal_modes.items())]
            L += ["  Working days exclude the terminal's weekend and its published closures."]
        L += [""]
    L += ["Signed for the Shipper and the Carrier."]
    return L


def write_agreement(world, vendor: str, agreement_no: str, path: Path) -> None:
    c = rl_canvas.Canvas(str(path), pagesize=LETTER, invariant=1)
    _, height = LETTER
    y = height - 54
    for line in agreement_lines(world, vendor, agreement_no):
        if y < 54:
            c.showPage()
            y = height - 54
        bold = line.startswith(("RATE AGREEMENT", "SCHEDULE A", "Clause"))
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 8.5)
        c.drawString(LEFT, y, line)
        y -= 11.5
    c.showPage()
    c.save()


def write_pdfs(invoices: list[Invoice], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    writers = {"table": _table, "lines": _lines, "consolidated": _consolidated}
    for inv in invoices:
        writers[inv.layout](inv, out_dir / f"{inv.vendor}_{inv.invoice_number}.pdf")


def _header(c, inv: Invoice, pagesize, company: str, strapline: str) -> float:
    width, height = pagesize
    y = height - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(LEFT, y, company)
    c.setFont("Helvetica", 8)
    c.drawString(LEFT, y - 12, strapline)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(width - LEFT, y, _title(inv))
    c.setFont("Helvetica", 9)
    y -= 40
    for label, value in (
        ("Invoice number", inv.invoice_number),
        ("Invoice date", inv.invoice_date.isoformat()),
        ("Currency", inv.currency),
        ("Booking", inv.booking_ref or "-"),
        ("Bill of lading", inv.bl_ref or "-"),
    ):
        c.drawString(LEFT, y, f"{label}:")
        c.drawString(LEFT + 110, y, str(value))
        y -= 13
    if inv.is_credit_note and inv.credit_for:
        c.drawString(LEFT, y, "Credit against:")
        c.drawString(LEFT + 110, y, inv.credit_for)
        y -= 13
    return y - 12


def _table(inv: Invoice, path: Path) -> None:
    c = rl_canvas.Canvas(str(path), pagesize=LETTER, invariant=1)
    width, _ = LETTER
    y = _header(c, inv, LETTER, "NORDVIK LINE",
                "Ocean transportation services - Atlanta GA")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(LEFT, y, "CODE")
    c.drawString(LEFT + 55, y, "DESCRIPTION")
    c.drawString(LEFT + 210, y, "CONTAINER")
    c.drawString(LEFT + 300, y, "B/L")
    c.drawRightString(width - LEFT, y, "AMOUNT USD")
    y -= 6
    c.line(LEFT, y, width - LEFT, y)
    y -= 14
    c.setFont("Helvetica", 9)
    for line in inv.lines:
        c.drawString(LEFT, y, line.charge_code)
        c.drawString(LEFT + 55, y, line.description)
        c.drawString(LEFT + 210, y, line.container_no or "-")
        c.drawString(LEFT + 300, y, line.bl_number or "-")
        c.drawRightString(width - LEFT, y, _us(line.amount))
        y -= 13
    y -= 4
    c.line(LEFT + 260, y, width - LEFT, y)
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LEFT + 300, y, "TOTAL DUE")
    c.drawRightString(width - LEFT, y, f"{_us(inv.total)} {inv.currency}")
    c.showPage()
    c.save()


def _lines(inv: Invoice, path: Path) -> None:
    c = rl_canvas.Canvas(str(path), pagesize=A4, invariant=1)
    width, _ = A4
    y = _header(c, inv, A4, "ATLAS OCEAN NV",
                "Zeevaartlaan 14, Antwerpen - VAT BE0844.219.771")
    c.setFont("Helvetica", 9)
    c.drawString(LEFT, y, "Charges:")
    y -= 16
    for line in inv.lines:
        text = (f"{line.charge_code}  {line.description}"
                f"{'  ' + line.container_no if line.container_no else ''}"
                f"  {inv.currency} {_eu(line.amount)}")
        c.drawString(LEFT + 10, y, text)
        y -= 13
    y -= 8
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LEFT, y, f"Totaal / Total {inv.currency} {_eu(inv.total)}")
    y -= 24
    c.setFont("Helvetica", 7)
    c.drawString(LEFT, y, "Payable within 30 days. Amounts in euro.")
    c.showPage()
    c.save()


def _consolidated(inv: Invoice, path: Path) -> None:
    c = rl_canvas.Canvas(str(path), pagesize=LETTER, invariant=1)
    width, _ = LETTER
    y = _header(c, inv, LETTER, "HARBORLINK LOGISTICS",
                "Freight forwarding and customs brokerage - Savannah GA")
    c.setFont("Helvetica", 8)
    c.drawString(LEFT, y, "Statement of destination charges, grouped by bill of lading.")
    y -= 20

    groups: dict[str, list] = {}
    for line in inv.lines:
        groups.setdefault(line.bl_number or "UNREFERENCED", []).append(line)

    for bl, lines in groups.items():
        c.setFont("Helvetica-Bold", 9)
        c.drawString(LEFT, y, f"B/L {bl}")
        y -= 14
        c.setFont("Helvetica", 9)
        subtotal = Decimal("0")
        for line in lines:
            c.drawString(LEFT + 14, y, line.charge_code)
            c.drawString(LEFT + 70, y, line.description)
            c.drawString(LEFT + 230, y, line.container_no or "")
            c.drawRightString(width - LEFT, y, _us(line.amount))
            subtotal += line.amount
            y -= 13
        c.setFont("Helvetica-Oblique", 9)
        c.drawRightString(width - LEFT, y, f"Subtotal {bl}  {_us(subtotal)}")
        y -= 20
        c.setFont("Helvetica", 9)

    c.line(LEFT + 260, y + 6, width - LEFT, y + 6)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LEFT + 300, y - 8, "TOTAL DUE")
    c.drawRightString(width - LEFT, y - 8, f"{_us(inv.total)} {inv.currency}")
    c.showPage()
    c.save()
