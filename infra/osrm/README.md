# Self-hosted OSRM (road routing)

Logistics asks OSRM for the road path through each pool's stops. The public demo server
(`router.project-osrm.org`) is shared and rate-limited, so run our own with the Geofabrik
"India - central zone" extract (covers Chhattisgarh).

## Docker Compose

```sh
docker compose --profile tools run --rm osrm-prepare   # once: download map + build graph (4-8 GB RAM, minutes)
docker compose up -d osrm logistics logistics-worker
```

Logistics reaches it at `OSRM_BASE_URL=http://osrm:5000` (the compose default). To use the public
demo server meanwhile: `OSRM_BASE_URL=http://router.project-osrm.org`. Refresh the map with
`FORCE=1 docker compose --profile tools run --rm osrm-prepare && docker compose restart osrm`.

## Without Docker (the team VM)

The VM cannot run Docker, so OSRM v6.0.0 is built from source into `~/osrm/install` and started by
`~/start-osrm.sh` (port 5000, data in `~/osrm/data`); `~/start-backend.sh` starts it first and sets
`OSRM_BASE_URL=http://127.0.0.1:5000`. Same `prepare.sh` steps, run by hand with the native
`osrm-extract / osrm-partition / osrm-customize` binaries.
