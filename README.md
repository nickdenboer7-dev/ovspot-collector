# OVspot Collector

Real-time public transport data pipeline powering [ovspot.nl](https://ovspot.nl) — 
a live vehicle map of the Netherlands.

This repository contains the public data-ingestion layer: KV6 collection, 
GTFS parsing, and AIS integration for ferry services.

## What it powers

- **Live bus/tram/metro positions** via KV6 (NDOV ZeroMQ)
- **Ferry positions via AIS** — GVB IJveerboten (Amsterdam) + Waddenveerboten (TESO, Doeksen, Wagenborg)
- **GTFS-RT enrichment** — trip matching, delay calculation, stop sequence
- **Position source tracking** — `Live` (KV6/AIS), `Geschat` (estimated), `Dienstregeling` (schedule-only)

## Live demo

👉 [ovspot.nl](https://ovspot.nl)

Click any vehicle to see the real-time popup:
- Current stop, next stop, ETA
- Full trip timeline with delay indicators
- Ferry variant: ship name, speed, heading from AIS

## Components

### KV6 collector (`kv6_collector.py`)
Connects to NDOV ZeroMQ PUB/SUB, parses KV6 position messages, converts 
RD New → WGS84, writes atomic JSON snapshots.

### GTFS parser (`gtfs_parser.py`)
Imports GTFS zip into SQLite (routes, trips, stops, stop times, shapes, 
calendar). Indexed for fast trip/stop lookups.

### AIS ferry integration (`gvb_ferry.py`)
WebSocket connection to aisstream.io, filters on 29 MMSI numbers:
- **GVB IJveer** (Amsterdam IJ): IJveer 50–56, 60–66
- **TESO** (Texel ferry): 2 vessels
- **Doeksen** (Terschelling/Vlieland): 6 vessels
- **Wagenborg** (Ameland/Schiermonnikoog): 7 vessels

AIS position overrides GTFS estimate when data is <120s old (GVB) or <300s old (Wadden).

## Requirements

- Python 3.11+
- `pyzmq` — KV6 collector
- `websockets` — AIS stream
- SQLite (stdlib)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `KV6_ZMQ_URL` | NDOV ZeroMQ endpoint |
| `KV6_OUTPUT_FILE` | JSON snapshot path |
| `AIS_API_KEY` | aisstream.io API key |
| `GTFS_ZIP` | GTFS input archive |
| `GTFS_DB` | SQLite output path |

## Data sources

- KV6: [NDOV Loket](https://www.ndovloket.nl/)
- GTFS: [OpenOV](https://gtfs.ovapi.nl/)
- AIS: [aisstream.io](https://aisstream.io/)

This repo contains code only — no GTFS archives, KV6 snapshots, AIS data or credentials.

## License

MIT — see `LICENSE`.
