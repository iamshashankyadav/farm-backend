"""Deterministic V1 dataset: the same SEED always produces the same people, farms and listings."""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

SEED = 20261114
PASSWORD = "Farm@12345"  # every seeded account uses this; never use it outside dev
TODAY = date(2026, 11, 15)  # fixed so harvest dates (and so the data) do not drift between runs

# (district, state, lat, lng): farms are scattered within ~15 km of these
DISTRICTS = [
    ("Durg", "Chhattisgarh", 21.1904, 81.2849),
    ("Raipur", "Chhattisgarh", 21.2514, 81.6296),
    ("Bilaspur", "Chhattisgarh", 22.0797, 82.1409),
    ("Jaipur", "Rajasthan", 26.9124, 75.7873),
    ("Nashik", "Maharashtra", 19.9975, 73.7898),
    ("Pune", "Maharashtra", 18.5204, 73.8567),
    ("Indore", "Madhya Pradesh", 22.7196, 75.8577),
    ("Ludhiana", "Punjab", 30.9010, 75.8573),
]
FIRST = [
    "Ramesh",
    "Sunita",
    "Mahesh",
    "Kavita",
    "Dinesh",
    "Meena",
    "Suresh",
    "Anita",
    "Rajesh",
    "Pooja",
    "Vijay",
    "Lata",
    "Anil",
    "Geeta",
    "Mohan",
    "Savita",
    "Prakash",
    "Rekha",
    "Ashok",
    "Usha",
]
LAST = [
    "Sahu",
    "Verma",
    "Patel",
    "Yadav",
    "Sharma",
    "Chauhan",
    "Patil",
    "Singh",
    "Deshmukh",
    "Gupta",
]
VILLAGES = [
    "Kumhari",
    "Dhamdha",
    "Patan",
    "Bhilai",
    "Mandir Hasaud",
    "Arang",
    "Sanganer",
    "Chomu",
    "Sinnar",
    "Niphad",
    "Baramati",
    "Mhow",
    "Depalpur",
    "Jagraon",
    "Khanna",
    "Tilda",
]
FARM_STYLE = [
    "Organic Farm",
    "Fresh Fields",
    "Kisan Farm",
    "Green Acres",
    "Krishi Kendra",
    "Harvest Farm",
]
VARIETIES = {
    "tomato": ["Desi", "Hybrid", "Cherry"],
    "onion": ["Red", "White"],
    "potato": ["Kufri Jyoti", "Chipsona"],
    "mango": ["Dasheri", "Langra", "Alphonso"],
    "banana": ["Robusta", "Elaichi"],
}
# crop id (must exist in catalog crops.py): (unit, price range per unit in rupees, qty range)
CROPS = {
    "tomato": ("kg", (18, 45), (40, 400)),
    "onion": ("kg", (15, 38), (100, 800)),
    "potato": ("kg", (14, 30), (100, 900)),
    "brinjal": ("kg", (20, 40), (30, 250)),
    "okra": ("kg", (30, 70), (20, 150)),
    "cauliflower": ("piece", (15, 40), (50, 300)),
    "cabbage": ("piece", (10, 30), (50, 300)),
    "carrot": ("kg", (25, 55), (40, 300)),
    "green-chilli": ("kg", (40, 110), (10, 80)),
    "peas": ("kg", (45, 90), (20, 120)),
    "spinach": ("bunch", (6, 18), (50, 300)),
    "coriander": ("bunch", (5, 15), (50, 300)),
    "mango": ("kg", (50, 140), (50, 500)),
    "banana": ("dozen", (30, 70), (30, 250)),
    "guava": ("kg", (35, 80), (30, 200)),
    "papaya": ("kg", (22, 50), (30, 200)),
}


@dataclass
class ListingSpec:
    crop_id: str
    variety: str | None
    description: str
    qty_available: float
    unit: str
    price_per_unit: float
    harvest_date: str
    is_organic: bool


@dataclass
class FarmSpec:
    name: str
    village: str
    district: str
    state: str
    lat: float
    lng: float
    listings: list[ListingSpec] = field(default_factory=list)


@dataclass
class FarmerSpec:
    name: str
    phone: str
    farms: list[FarmSpec]


@dataclass
class CustomerSpec:
    name: str
    phone: str
    lat: float
    lng: float


@dataclass
class Dataset:
    farmers: list[FarmerSpec]
    customers: list[CustomerSpec]


def build_dataset(farmers: int = 20, customers: int = 40, seed: int = SEED) -> Dataset:
    rng = random.Random(seed)
    crop_ids = list(CROPS)
    out_farmers: list[FarmerSpec] = []
    for i in range(farmers):
        district, state, dlat, dlng = DISTRICTS[i % len(DISTRICTS)]
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        farm_list = []
        for _ in range(rng.choice([1, 1, 2])):
            listings = []
            for crop_id in rng.sample(crop_ids, rng.randint(3, 6)):
                unit, (lo, hi), (qlo, qhi) = CROPS[crop_id]
                variety = rng.choice(VARIETIES[crop_id]) if crop_id in VARIETIES else None
                organic = rng.random() < 0.3
                listings.append(
                    ListingSpec(
                        crop_id=crop_id,
                        variety=variety,
                        description=f"{'Organically grown, ' if organic else ''}picked fresh from our fields.",
                        qty_available=float(rng.randint(qlo, qhi)),
                        unit=unit,
                        price_per_unit=float(rng.randint(lo, hi)),
                        harvest_date=(TODAY - timedelta(days=rng.randint(0, 4))).isoformat(),
                        is_organic=organic,
                    )
                )
            farm_list.append(
                FarmSpec(
                    name=f"{name.split()[1]} {rng.choice(FARM_STYLE)}",
                    village=rng.choice(VILLAGES),
                    district=district,
                    state=state,
                    lat=round(dlat + rng.uniform(-0.13, 0.13), 5),
                    lng=round(dlng + rng.uniform(-0.13, 0.13), 5),
                    listings=listings,
                )
            )
        out_farmers.append(FarmerSpec(name=name, phone=f"+91900010{i:04d}", farms=farm_list))

    out_customers = []
    for i in range(customers):
        _, _, dlat, dlng = DISTRICTS[rng.randrange(len(DISTRICTS))]
        out_customers.append(
            CustomerSpec(
                name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                phone=f"+91900020{i:04d}",
                lat=round(dlat + rng.uniform(-0.08, 0.08), 5),
                lng=round(dlng + rng.uniform(-0.08, 0.08), 5),
            )
        )
    return Dataset(farmers=out_farmers, customers=out_customers)


# ---- V2 (land) and order plans -------------------------------------------------------------

SEASONS = [("Kharif", "2026-06-15", "2026-10-31"), ("Rabi", "2026-11-15", "2027-03-31")]
PLOT_CROPS = [
    "tomato",
    "onion",
    "potato",
    "brinjal",
    "okra",
    "cabbage",
    "carrot",
    "peas",
    "spinach",
]
NOTES = [
    "Seeds sown, soil moist.",
    "First leaves are out.",
    "Weeding done this week.",
    "Flowering has started.",
    "Good growth after the rain.",
]
STAGES = ["SOWN", "GROWING", "FLOWERING"]


@dataclass
class PlotSpec:
    title: str
    ring: list[list[float]]  # closed ring of [lng, lat]
    soil_type: str
    water_source: str
    price_per_kg: float
    crops: list[str]


@dataclass
class ReservationPlan:
    farmer_index: int
    plot_index: int
    season: str
    customer_index: int
    crop_id: str
    qty_kg: float
    stage: str  # how far it is taken: PENDING, ACCEPTED, ACTIVE (accepted + deposit paid)
    updates: list[tuple[str, str]]


@dataclass
class OrderPlan:
    customer_index: int
    farmer_indices: list[int]  # which farmers' listings to buy from
    picks: list[int]  # index into each farmer's listing list
    qty: list[float]


@dataclass
class V2Plan:
    plots: dict[int, list[PlotSpec]]  # farmer index -> plots
    reservations: list[ReservationPlan]
    orders: list[OrderPlan]


def _square(lat: float, lng: float, side_m: float) -> list[list[float]]:
    d_lat = side_m / 111_000 / 2
    d_lng = side_m / (111_000 * 0.9) / 2  # good enough at Indian latitudes
    pts = [
        [lng - d_lng, lat - d_lat],
        [lng + d_lng, lat - d_lat],
        [lng + d_lng, lat + d_lat],
        [lng - d_lng, lat + d_lat],
    ]
    pts = [[round(x, 6), round(y, 6)] for x, y in pts]
    return [*pts, pts[0]]


def build_v2_plan(data: Dataset, orders: int = 200, seed: int = SEED) -> V2Plan:
    rng = random.Random(seed + 1)
    plots: dict[int, list[PlotSpec]] = {}
    for i, farmer in enumerate(data.farmers):
        farm = farmer.farms[0]
        n = rng.choice([1, 2, 2, 3])
        plots[i] = []
        for k in range(n):
            side = rng.uniform(80, 130)  # about 1.6 to 4 acres
            # plots sit in a row 300 m apart so they never overlap
            plots[i].append(
                PlotSpec(
                    title=f"{farmer.name.split()[1]} plot {k + 1}, {farm.village}",
                    ring=_square(farm.lat + 0.004, farm.lng + 0.004 * (k + 1), side),
                    soil_type=rng.choice(["Black soil", "Red soil", "Alluvial", "Loam"]),
                    water_source=rng.choice(["Borewell", "Canal", "River", "Rain-fed"]),
                    price_per_kg=float(rng.randint(15, 60)),
                    crops=rng.sample(PLOT_CROPS, rng.randint(3, 5)),
                )
            )

    reservations: list[ReservationPlan] = []
    taken: set[tuple[int, int, str]] = set()
    for _ in range(max(1, len(data.farmers) * 2)):
        f = rng.randrange(len(data.farmers))
        p = rng.randrange(len(plots[f]))
        season = rng.choice(SEASONS)[0]
        if (f, p, season) in taken:
            continue
        taken.add((f, p, season))
        stage = rng.choices(["PENDING", "ACCEPTED", "ACTIVE"], weights=[2, 1, 4])[0]
        count = rng.randint(1, 3) if stage == "ACTIVE" else 0
        updates = [(STAGES[j], rng.choice(NOTES)) for j in range(count)]
        reservations.append(
            ReservationPlan(
                farmer_index=f,
                plot_index=p,
                season=season,
                customer_index=rng.randrange(len(data.customers)),
                crop_id=rng.choice(plots[f][p].crops),
                qty_kg=float(rng.randint(100, 900)),
                stage=stage,
                updates=updates,
            )
        )

    order_plans: list[OrderPlan] = []
    for _ in range(orders):
        farmers = rng.sample(range(len(data.farmers)), rng.choice([1, 1, 2]))
        order_plans.append(
            OrderPlan(
                customer_index=rng.randrange(len(data.customers)),
                farmer_indices=farmers,
                picks=[rng.randrange(3) for _ in farmers],
                qty=[float(rng.randint(1, 5)) for _ in farmers],
            )
        )
    return V2Plan(plots=plots, reservations=reservations, orders=order_plans)
