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
