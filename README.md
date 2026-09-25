# OVspot Data Tools

Small, standalone data-ingestion tools extracted from the OVspot project.

This repository intentionally contains **only** a public KV6 collector and a
GTFS-to-SQLite parser. It does not contain the OVspot website, map renderer,
admin interface, API application, analytics, deployment configuration, or
production credentials.

## Components

### KV6 collector

`src/kv6_collector.py` connects to an NDOV ZeroMQ PUB/SUB endpoint, accepts
gzip-compressed KV6 messages, parses common position records, converts Dutch
RD New coordinates to WGS84 and periodically writes an atomic JSON snapshot.

The public collector has deliberately been decoupled from OVspot's private
runtime store, trip enrichment, speed estimation, KV17 state, web API and
renderer.

### GTFS parser

`src/gtfs_parser.py` imports a GTFS zip archive into SQLite. It stores routes,
agencies, trips, stops, stop times, shapes and calendar dates and adds indexes
for common lookup paths.

## Requirements

- Python 3.11+
- `pyzmq` for the KV6 collector
- SQLite support from the Python standard library

Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the example environment file if you want to override defaults:

```bash
cp .env.example .env
```

The scripts do not load `.env` automatically. Export variables in your shell,
use a process manager, or use your preferred dotenv loader.

### KV6 variables

- `KV6_ZMQ_URL` — ZeroMQ endpoint
- `KV6_OUTPUT_FILE` — JSON snapshot destination
- `KV6_VEHICLE_TIMEOUT` — seconds before a vehicle is removed
- `KV6_SAVE_INTERVAL` — snapshot interval in seconds
- `KV6_SUBSCRIBE_PREFIX` — ZeroMQ subscription prefix
- `KV6_RECEIVE_HWM` — receive high-water mark

Run:

```bash
python src/kv6_collector.py
```

### GTFS variables

- `GTFS_ZIP` — input GTFS zip archive
- `GTFS_DB` — output SQLite database

Run:

```bash
python src/gtfs_parser.py --input ./data/gtfs.zip --output ./data/gtfs.db
```

## Repository structure

```text
.
├── src/
│   ├── kv6_collector.py
│   └── gtfs_parser.py
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

## Data and licensing

This repository contains code only. It does not redistribute GTFS archives,
live KV6 payloads, snapshots, databases or other operational data. Check the
terms of the data source you use before redistributing derived data.

## Security

No production API keys, passwords, cookies, server paths, private IP
addresses, databases, logs, backups or deployment files are included.
Configuration is supplied through environment variables.

## License

Code in this repository is released under the MIT License. See `LICENSE`.
