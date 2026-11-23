#!/bin/sh
# One-off: download the Geofabrik "India - central zone" extract (covers Chhattisgarh) and build
# the OSRM routing graph (MLD) into /data. Needs about 4-8 GB of RAM and a few minutes.
#   docker compose --profile tools run --rm osrm-prepare
# Re-run it (with FORCE=1) to refresh the map; then `docker compose restart osrm`.
set -eu
cd /data
PBF=central-zone-latest.osm.pbf
if [ ! -f "$PBF" ] || [ "${FORCE:-0}" = 1 ]; then
  wget -O "$PBF" https://download.geofabrik.de/asia/india/central-zone-latest.osm.pbf
fi
osrm-extract -p /opt/car.lua "$PBF"
osrm-partition central-zone-latest.osrm
osrm-customize central-zone-latest.osrm
rm -f "$PBF"   # the graph is all the router needs
echo "OSRM data ready in /data"
