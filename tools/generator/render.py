"""Vendor PDF layouts (reportlab). Text-based PDFs only — no OCR anywhere.

Four layouts, one per vendor, chosen so that a single naive regex does not work
across vendors:
  table        NORDVIK    : header block + one ruled table (code | description | container | amount)
  keyvalue     MERIDIAN   : "Label: value" blocks per container, totals at bottom
  lines        ATLASOCEAN : free-text charge lines "OFR Ocean freight NVKU1234567 EUR 2.650,00"
                            (European number format, EUR)
  consolidated HARBORLINK : statement grouped by B/L, per-B/L subtotals, one grand total

Each writer must:
  * print invoice number, invoice date, vendor name, currency, booking and/or B/L
    reference exactly as stored on the Invoice object (T09 relies on this),
  * print every line in Invoice.lines order (line_no in truth follows it),
  * print a total that equals Invoice.total,
  * for credit notes, title "CREDIT NOTE", reference `credit_for`, negative amounts.

Fonts: built-in Helvetica only (deterministic, no font fetch). Page size A4 for
ATLASOCEAN, Letter for the others — a small realism detail that also breaks
bbox-based extraction copied across vendors.
"""
from __future__ import annotations

from pathlib import Path

from models import Invoice


def write_pdfs(invoices: list[Invoice], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for inv in invoices:
        writer = {"table": _table, "keyvalue": _keyvalue, "lines": _lines, "consolidated": _consolidated}[inv.layout]
        writer(inv, out_dir / f"{inv.vendor}_{inv.invoice_number}.pdf")


def _table(inv: Invoice, path: Path) -> None:
    raise NotImplementedError


def _keyvalue(inv: Invoice, path: Path) -> None:
    raise NotImplementedError


def _lines(inv: Invoice, path: Path) -> None:
    raise NotImplementedError


def _consolidated(inv: Invoice, path: Path) -> None:
    raise NotImplementedError
