#!/bin/sh
# One-off: download the Geofabrik "India - central zone" extract, clip it to the Durg area
# (Durg, Bhilai, Raipur, Rajnandgaon, Bemetara, Balod, Dhamtari) and build the OSRM routing graph
# (MLD) into /data. The clip is small (about 7 MB), so this takes a minute and little RAM.
#   docker compose --profile tools run --rm osrm-prepare
# Other area: BBOX=min_lon,min_lat,max_lon,max_lat. Refresh: FORCE=1, then `docker compose restart osrm`.
set -eu
cd /data
BBOX="${BBOX:-80.8,20.5,82.0,21.9}"
if [ ! -f durg.osrm.mldgr ] || [ "${FORCE:-0}" = 1 ]; then
  command -v osmium >/dev/null || { apt-get update -qq && apt-get install -y -qq osmium-tool wget; }
  wget -O central.pbf https://download.geofabrik.de/asia/india/central-zone-latest.osm.pbf
  osmium extract -b "$BBOX" --strategy complete_ways -o durg.osm.pbf central.pbf --overwrite
  rm central.pbf
  osrm-extract -p /opt/car.lua durg.osm.pbf
  osrm-partition durg.osrm
  osrm-customize durg.osrm
  rm -f durg.osm.pbf
fi
echo "OSRM data ready in /data"
