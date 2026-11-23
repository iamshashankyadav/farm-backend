# Self-hosted OSRM (road routing)

Logistics asks OSRM for the road path through each pool's stops. The public demo server
(`router.project-osrm.org`) is shared and rate-limited, so run our own with the Geofabrik
"India - central zone" extract clipped to the Durg area (Durg, Bhilai, Raipur, Rajnandgaon,
Bemetara, Balod, Dhamtari; bbox `80.8,20.5,82.0,21.9`, about 7 MB). Routes outside it fail and the
app falls back to straight lines.

## Docker Compose

```sh
docker compose --profile tools run --rm osrm-prepare   # once: download map + build graph (about a minute)
docker compose up -d osrm logistics logistics-worker
```

Logistics reaches it at `OSRM_BASE_URL=http://osrm:5000` (the compose default). To use the public
demo server meanwhile: `OSRM_BASE_URL=http://router.project-osrm.org`. Refresh the map with
`FORCE=1 docker compose --profile tools run --rm osrm-prepare && docker compose restart osrm`.

## Without Docker (the team VM)

The VM cannot run Docker, so OSRM v6.0.0 is built from source into `~/osrm/install` and started by
`~/start-osrm.sh` (port 5100, since 5000 is MinIO; data in `~/osrm/data`); `~/start-backend.sh` starts it first and sets
`OSRM_BASE_URL=http://127.0.0.1:5000`. Same `prepare.sh` steps, run by hand with the native
`osrm-extract / osrm-partition / osrm-customize` binaries.
