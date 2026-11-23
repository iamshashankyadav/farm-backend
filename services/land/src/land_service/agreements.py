"""Reservation agreements (HLD section 12, "Reserve a plot", step 4).

When the farmer accepts a reservation an agreement is generated with the price, the deposit and
the harvest terms, so both sides see exactly what they agreed to. The text is built here from the
reservation, its plot-season and the plot; the row is written in the same transaction as the
acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

HARVEST_OPTIONS = ("DELIVERY", "BUYBACK")


@dataclass(frozen=True)
class AgreementTerms:
    total: float
    deposit: float
    balance: float
    terms: list[str]


def _rupees(amount: float) -> str:
    return f"₹{amount:,.0f}" if amount == int(amount) else f"₹{amount:,.2f}"


def build_terms(
    *,
    plot_title: str,
    area_acres: float,
    season: str,
    start_date: date,
    end_date: date,
    crop_id: str,
    expected_qty_kg: float,
    price_per_kg: float,
    deposit_rate: float,
) -> AgreementTerms:
    total = round(price_per_kg * expected_qty_kg, 2)
    deposit = round(total * deposit_rate, 2)
    balance = round(total - deposit, 2)
    crop = crop_id.replace("-", " ")
    terms = [
        (
            f"The customer reserves “{plot_title}” ({area_acres:g} acres) for the {season} season, "
            f"{start_date:%d %b %Y} to {end_date:%d %b %Y}, to grow {crop} (about {expected_qty_kg:g} kg)."
        ),
        (
            f"Price {_rupees(total)} ({_rupees(price_per_kg)} per kg). A deposit of {_rupees(deposit)} "
            f"({deposit_rate:.0%}) is due now; the balance of {_rupees(balance)} is settled when the harvest "
            "order completes."
        ),
        "The plot-season becomes ACTIVE once the deposit is paid and is not offered to anyone else.",
        "The farmer grows the crop and posts progress updates with geotagged photos at each stage.",
        (
            "At harvest the farmer records the weight harvested; the price is the agreed rate per kg "
            "for that weight. The customer then chooses home delivery or buy-back (the farmer sells the "
            "produce and credits the customer 90% of its value)."
        ),
        (
            "After delivery the customer rates the harvest; the rating is shown to future customers "
            "of this farmer."
        ),
        "Either side can cancel before the harvest; a deposit already paid is refunded in full.",
    ]
    return AgreementTerms(total=total, deposit=deposit, balance=balance, terms=terms)
