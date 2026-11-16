import argparse
import os

from farm_seed.client import Gateway
from farm_seed.data import build_dataset
from farm_seed.v1 import as_dict, seed_v1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="farm_seed", description="Fill the platform with dummy V1 data"
    )
    parser.add_argument("--base-url", default=os.getenv("SEED_BASE_URL", "http://localhost/api/v1"))
    parser.add_argument("--admin-phone", default=os.getenv("SEED_ADMIN_PHONE"))
    parser.add_argument("--admin-password", default=os.getenv("SEED_ADMIN_PASSWORD"))
    parser.add_argument("--farmers", type=int, default=20)
    parser.add_argument("--customers", type=int, default=40)
    args = parser.parse_args()
    if not (args.admin_phone and args.admin_password):
        parser.error(
            "give --admin-phone and --admin-password (or SEED_ADMIN_PHONE / SEED_ADMIN_PASSWORD)"
        )
    summary = seed_v1(
        Gateway(args.base_url),
        build_dataset(args.farmers, args.customers),
        args.admin_phone,
        args.admin_password,
    )
    print("Seeded:", as_dict(summary))


if __name__ == "__main__":
    main()
