"""Serialise the World into the files the agent (and the verifier) receive.

File contracts (these ARE the data schema the task ships; keep in sync with policy.md):

shipments.json
  {"bookings": [{"booking_id", "vendor", "bl_number", "pol", "pod", "sailing_date",
                 "eta", "containers": [{"container_no", "type", "booked_kg", "gross_kg",
                 "cbm", "gate_out_date", "empty_return_date", "terminal",
                 "sales_orders": [{"so", "gross_kg", "cbm", "value_usd"}]}]}]}

contracts/<VENDOR>.json
  {"vendor", "currency",
   "versions": [{"valid_from", "valid_to",
                 "lanes": {"USSAV-AEJEA": {"20DV": 1850.00, "40HC": 2900.00}},
                 "minimum_ocean_freight": {"20DV": 0, "40HC": 2200.00},
                 "index_surcharges": {"BAF": {"2024-02": {"20DV": 310, "40HC": 620}}},
                 "accessorials": {"DOC": {"basis": "per_bl", "amount": 95.00},
                                  "THC_O": {"basis": "per_container", "amount": {"20DV": 260, "40HC": 340}}},
                 "overweight": {"threshold_kg": 20000, "amount": {"20DV": 120, "40HC": 150}},
                 "detention": {"free_days": 7,
                               "tiers": [{"from_day": 1, "to_day": 7, "rate": {"20DV": 75, "40HC": 110}},
                                         {"from_day": 8, "to_day": null, "rate": {"20DV": 130, "40HC": 190}}],
                               "terminal_mode": {"AEJEA-T1": "calendar", "AEJEA-T2": "working"}}}]}

holidays.json   {"AEJEA-T2": ["2024-04-10", "2024-04-11"], ...}
fx.csv          date,EUR_USD   (one row per fixing day; weekends absent on purpose — policy §3.8)
"""
from __future__ import annotations

import json
from pathlib import Path

from models import World


def write_data(world: World, out: Path) -> None:
    (out / "contracts").mkdir(parents=True, exist_ok=True)
    raise NotImplementedError("serialise per module docstring; Decimal -> str/float with 2 dp")
