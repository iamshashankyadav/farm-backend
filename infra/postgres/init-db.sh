#!/bin/sh
# Runs once, when the Postgres data volume is first created.
# One schema per service, owned by its own login role, so a service cannot read another's tables.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE EXTENSION IF NOT EXISTS postgis;
-- land: an exclusion constraint keeps the seasons of one plot from overlapping (uuid in GiST)
CREATE EXTENSION IF NOT EXISTS btree_gist;
SQL

for svc in identity catalog land media order logistics notification; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE "farm_${svc}" LOGIN PASSWORD '${POSTGRES_PASSWORD}';
CREATE SCHEMA "${svc}" AUTHORIZATION "farm_${svc}";
-- PostGIS types and functions live in public, so keep it on the path
ALTER ROLE "farm_${svc}" SET search_path = "${svc}", public;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO "farm_${svc}";
SQL
done
