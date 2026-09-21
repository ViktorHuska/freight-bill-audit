# Freight Invoice Audit Procedure — International Sales Office

Revision 7. Applies to all ocean-freight, accessorial and detention invoices
received from carriers and forwarders for export shipments.

## 1. Scope and inputs

An audit batch consists of the PDF invoices in the batch folder, the shipment
register (`shipments.json`), the vendor rate contracts (`contracts/*.json`), the
terminal holiday calendar (`holidays.json`) and the FX fixings (`fx.csv`).
Every charge line on every invoice receives exactly one decision. The audit
result is written as `audit.json`; the allocation of approved cost to sales
orders is written as `landed_cost.csv` (schema in section 8).

## 2. Matching an invoice to shipments

1. An invoice references one or more shipments by booking number and/or bill of
   lading (B/L) number, and lists container numbers on its charge lines.
2. Match on B/L number first, then on booking number. If neither reference
   matches the register but every container number on the invoice belongs to
   exactly one booking in the register, treat the invoice as matched to that
   booking and record the reference as a vendor typo. A container number is
   authoritative; a booking or B/L string is not.
3. An invoice whose charges cannot be tied to any booking by any of the above
   is `UNMATCHED`: every line is disputed with reason `UNMATCHED`.
4. A single invoice may cover several bookings (forwarder consolidations). Each
   charge line is matched to the booking that owns the container it names, or,
   for per-B/L charges, to the B/L it names.

## 3. Computing the expected amount of a charge

### 3.1 Contract selection
The applicable contract version is the version of the **invoicing vendor's**
contract whose validity window contains the booking's **sailing date**. Invoice
date and issue date are irrelevant to rate selection.

### 3.2 Charge codes and basis
Each contract lists the charge codes the vendor may bill and the basis of each:
`per_container`, `per_bl`, or `per_shipment`. A charge billed on a basis other
than its contractual basis (for example a `per_bl` documentation fee billed once
for each container) has an expected amount equal to what the contractual basis
yields for the whole invoice; the excess is disputed with reason `BASIS_ERROR`.

### 3.3 Ocean freight
Expected ocean freight = lane rate for the container type, from the applicable
contract version, for the lane `POL-POD` of the booking. If the contract defines
a minimum ocean freight per container and the lane rate is below it, the
minimum applies.

### 3.4 Surcharges indexed by period
Surcharges with an index table (bunker/fuel, emergency and similar) are read from
the table row for the **month of the sailing date**, not the month of the
invoice date.

### 3.5 Overweight
If the contract defines an overweight surcharge, it applies when the container's
**actual gross weight from the packing list** (the `gross_kg` value recorded for
the container in the register) exceeds the threshold. Booked weight is
irrelevant.

### 3.6 Detention
Detention is billed per container per day beyond the free period. The number of
chargeable days is computed as follows:

* Day 1 is the day after the container is gated out of the destination
  terminal. The empty-return day is included.
* Counting mode is defined per terminal in the contract: `calendar` counts every
  day; `working` counts Monday–Friday only and skips the dates listed for that
  terminal in `holidays.json`. Free days are counted in the same mode.
* Chargeable days = counted days − free days (minimum 0). Rates are tiered by
  chargeable day number; a day's rate is the rate of the tier containing it.

### 3.7 Charges not in the contract
A charge code that the applicable contract does not list has an expected amount
of 0.00 and is disputed with reason `UNAUTHORIZED_CHARGE`, regardless of how it
is described on the invoice.

### 3.8 Foreign-currency invoices
Invoices in EUR are converted to USD using the `EUR_USD` fixing from `fx.csv`
for the **sailing date** of the matched booking. If the sailing date has no
fixing, use the most recent earlier fixing. Convert each line individually and
round to cents after conversion. Both `billed_amount` and `expected_amount` in
`audit.json` are reported in USD; `billed_amount_original` carries the invoice
currency figure.

### 3.9 Rounding
All expected amounts are rounded half-up to cents after the full computation of
the line, never at intermediate steps.

## 4. Decisions

For each line, `variance = billed_amount − expected_amount` (USD).

| Condition | decision | reason |
|---|---|---|
| \|variance\| ≤ 2.00 and no other rule applies | `APPROVE` | `OK` if variance is 0.00, otherwise `WITHIN_TOLERANCE` |
| line on a duplicate invoice (section 5.1) | `DISPUTE` | `DUPLICATE_INVOICE` |
| line on an unmatched invoice | `DISPUTE` | `UNMATCHED` |
| charge code not in contract | `DISPUTE` | `UNAUTHORIZED_CHARGE` |
| charge billed on the wrong basis | `DISPUTE` | `BASIS_ERROR` |
| variance < −2.00 (vendor under-billed) | `APPROVE` | `UNDERBILLED` |
| variance > 2.00, indexed surcharge taken from the wrong period | `DISPUTE` | `WRONG_SURCHARGE_PERIOD` |
| variance > 2.00, different contract version used | `DISPUTE` | `CONTRACT_VERSION` |
| variance > 2.00, chargeable detention days differ | `DISPUTE` | `FREE_TIME_MISCOUNT` |
| variance > 2.00, EUR converted at the wrong date | `DISPUTE` | `FX_RATE` |
| variance > 2.00, no cause attributable | `DISPUTE` | `RATE_MISMATCH` |

A cause is attributed to a variance only when recomputing the line under that
single wrong assumption reproduces the billed amount within 0.01 USD. The
assumptions to test, in order, are: the indexed surcharge read from the month of
the **invoice date** (`WRONG_SURCHARGE_PERIOD`); the contract version selected
by the **invoice date** (`CONTRACT_VERSION`); detention counted in `calendar`
mode ignoring holidays, or with the free period not deducted
(`FREE_TIME_MISCOUNT`); the EUR conversion taken at the fixing for the
**invoice date** (`FX_RATE`). If no assumption reproduces the billed amount, the
reason is `RATE_MISMATCH`. When several rows of the table apply, the reason is
the **first** matching row. An approved line is paid at `billed_amount`;
a disputed line is paid at `expected_amount`. The **approved amount** of a line
is therefore `billed_amount` for `APPROVE` and `expected_amount` for `DISPUTE`.

## 5. Duplicates and credit notes

### 5.1 Duplicates
An invoice is a duplicate of an earlier invoice from the same vendor when both
reference the same B/L or booking, list the same charge codes on the same
containers, and their totals agree within 0.01 in the invoice currency. The
earlier invoice (by invoice date, then by invoice number) is the original; the
later one has status `DUPLICATE` and every line is disputed with reason
`DUPLICATE_INVOICE` and approved amount 0.00.

### 5.2 Credit notes
A credit note (negative total) references the invoice it corrects. Its lines are
approved as billed (negative amounts) with reason `CREDIT_NOTE` and status
`CREDIT_NOTE`. Its approved amounts are allocated exactly like a charge, so they
reduce landed cost.

## 6. Invoice status

`APPROVED` when every line is `APPROVE`; `DISPUTED` when every line is
`DISPUTE`; `PARTIALLY_DISPUTED` otherwise; `DUPLICATE`, `CREDIT_NOTE` and
`UNMATCHED` as defined above.

## 7. Allocation of approved cost to sales orders

1. Only approved amounts (section 4) are allocated. Duplicate and unmatched
   invoices allocate nothing.
2. A `per_container` charge is allocated to the sales-order lines loaded in that
   container in proportion to their `gross_kg`.
3. A `per_bl` or `per_shipment` charge is first split equally across the
   containers of that B/L (or booking), then allocated as in step 2.
4. A sales order that is loaded in several containers or ships on several B/Ls
   accumulates its share from each.
5. Rounding: allocate each charge line separately using the largest-remainder
   method at cents so that the allocated shares of a line sum exactly to the
   line's approved amount. Then sum per sales order and per charge category.
6. Charge categories for `landed_cost.csv`: `ocean_freight` (charge code
   `OFR`), `surcharges` (all indexed and overweight codes), `accessorials`
   (documentation, terminal handling, seal and similar), `detention` (`DET`).

## 8. Output schema

### 8.1 `audit.json`
```json
{
  "batch": "<name of the invoices directory>",
  "invoices": [
    {
      "invoice_number": "string",
      "vendor": "string (contract vendor code)",
      "invoice_date": "YYYY-MM-DD",
      "currency": "USD|EUR",
      "status": "APPROVED|PARTIALLY_DISPUTED|DISPUTED|DUPLICATE|CREDIT_NOTE|UNMATCHED",
      "duplicate_of": "invoice_number or null",
      "matched_bookings": ["booking_id", "..."],
      "invoice_total_usd": 0.00,
      "approved_total_usd": 0.00,
      "lines": [
        {
          "line_no": 1,
          "charge_code": "string",
          "container_no": "string or null",
          "bl_number": "string or null",
          "billed_amount_original": 0.00,
          "billed_amount": 0.00,
          "expected_amount": 0.00,
          "variance": 0.00,
          "decision": "APPROVE|DISPUTE",
          "reason": "OK|WITHIN_TOLERANCE|UNDERBILLED|RATE_MISMATCH|WRONG_SURCHARGE_PERIOD|CONTRACT_VERSION|FREE_TIME_MISCOUNT|BASIS_ERROR|UNAUTHORIZED_CHARGE|FX_RATE|DUPLICATE_INVOICE|UNMATCHED|CREDIT_NOTE"
        }
      ]
    }
  ]
}
```
Invoices are ordered by `invoice_number`; lines keep the order printed on the
invoice, numbered from 1. All amounts are numbers with two decimals.

### 8.2 `landed_cost.csv`
Header exactly: `sales_order,ocean_freight,surcharges,accessorials,detention,total`
One row per sales order that appears in the register, sorted by `sales_order`,
amounts in USD with two decimals, `total` = sum of the four categories. Sales
orders with no approved cost appear with zeros.
