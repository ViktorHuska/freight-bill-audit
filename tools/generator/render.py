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
    c = rl_canvas.Canvas(str(path), pagesize=LETTER)
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
    c = rl_canvas.Canvas(str(path), pagesize=A4)
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
    c = rl_canvas.Canvas(str(path), pagesize=LETTER)
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
