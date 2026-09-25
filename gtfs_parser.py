#!/usr/bin/env python3
"""Import a GTFS zip archive into a compact SQLite database."""

from __future__ import annotations

import argparse
import csv
import io
import os
import sqlite3
import time
import zipfile


def safe_float(value):
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def safe_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def build_database(zip_path: str, db_path: str) -> None:
    db_tmp = db_path + ".import_tmp"
    started = time.time()

    if os.path.exists(db_tmp):
        os.remove(db_tmp)

    con = sqlite3.connect(db_tmp)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=-32000")
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE routes (
        route_id TEXT PRIMARY KEY,
        line TEXT,
        route_name TEXT,
        agency_id TEXT,
        route_type INTEGER,
        route_color TEXT,
        route_text_color TEXT,
        route_url TEXT
    );
    CREATE TABLE agencies (
        agency_id TEXT PRIMARY KEY,
        agency_name TEXT,
        agency_url TEXT,
        agency_timezone TEXT,
        agency_phone TEXT
    );
    CREATE TABLE trips (
        trip_id TEXT PRIMARY KEY,
        realtime_trip_id TEXT,
        service_id TEXT,
        destination TEXT,
        route_id TEXT,
        shape_id TEXT,
        trip_short_name TEXT,
        block_id TEXT,
        direction_id INTEGER
    );
    CREATE TABLE stops (
        stop_id TEXT PRIMARY KEY,
        stop_code TEXT,
        stop_name TEXT,
        lat REAL,
        lon REAL,
        parent_station TEXT,
        location_type INTEGER,
        platform_code TEXT
    );
    CREATE TABLE stop_times (
        trip_id TEXT,
        stop_id TEXT,
        stop_sequence INTEGER,
        arrival_time TEXT,
        departure_time TEXT,
        shape_dist_traveled REAL,
        stop_headsign TEXT
    );
    CREATE TABLE shapes (
        shape_id TEXT,
        lat REAL,
        lon REAL,
        seq INTEGER,
        shape_dist_traveled REAL
    );
    CREATE TABLE calendar_dates (
        service_id TEXT,
        date TEXT,
        exception_type INTEGER
    );
    """)

    with zipfile.ZipFile(zip_path) as archive:
        def reader(name: str):
            return csv.DictReader(
                io.TextIOWrapper(archive.open(name), encoding="utf-8-sig")
            )

        for row in reader("routes.txt"):
            cur.execute(
                "INSERT INTO routes VALUES (?,?,?,?,?,?,?,?)",
                (
                    row["route_id"],
                    row.get("route_short_name", ""),
                    row.get("route_long_name", ""),
                    row.get("agency_id", ""),
                    safe_int(row.get("route_type")),
                    row.get("route_color", ""),
                    row.get("route_text_color", ""),
                    row.get("route_url", ""),
                ),
            )

        if "agency.txt" in archive.namelist():
            for row in reader("agency.txt"):
                cur.execute(
                    "INSERT OR REPLACE INTO agencies VALUES (?,?,?,?,?)",
                    (
                        row.get("agency_id", ""),
                        row.get("agency_name", ""),
                        row.get("agency_url", ""),
                        row.get("agency_timezone", ""),
                        row.get("agency_phone", ""),
                    ),
                )

        for row in reader("trips.txt"):
            cur.execute(
                "INSERT INTO trips VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    row["trip_id"],
                    row.get("realtime_trip_id", ""),
                    row.get("service_id", ""),
                    row.get("trip_headsign", ""),
                    row.get("route_id", ""),
                    row.get("shape_id") or None,
                    row.get("trip_short_name") or None,
                    row.get("block_id") or None,
                    safe_int(row.get("direction_id")),
                ),
            )

        for row in reader("stops.txt"):
            cur.execute(
                "INSERT INTO stops VALUES (?,?,?,?,?,?,?,?)",
                (
                    row["stop_id"],
                    row.get("stop_code", ""),
                    row.get("stop_name", ""),
                    safe_float(row.get("stop_lat")),
                    safe_float(row.get("stop_lon")),
                    row.get("parent_station") or None,
                    safe_int(row.get("location_type")),
                    row.get("platform_code") or None,
                ),
            )

        batch = []
        for row in reader("stop_times.txt"):
            batch.append(
                (
                    row["trip_id"],
                    row["stop_id"],
                    int(row["stop_sequence"]),
                    row.get("arrival_time", ""),
                    row.get("departure_time", ""),
                    safe_float(row.get("shape_dist_traveled")),
                    row.get("stop_headsign") or None,
                )
            )
            if len(batch) >= 100000:
                cur.executemany(
                    "INSERT INTO stop_times VALUES (?,?,?,?,?,?,?)", batch
                )
                batch = []
        if batch:
            cur.executemany(
                "INSERT INTO stop_times VALUES (?,?,?,?,?,?,?)", batch
            )

        if "shapes.txt" in archive.namelist():
            batch = []
            for row in reader("shapes.txt"):
                batch.append(
                    (
                        row["shape_id"],
                        safe_float(row.get("shape_pt_lat")),
                        safe_float(row.get("shape_pt_lon")),
                        int(row.get("shape_pt_sequence", 0)),
                        safe_float(row.get("shape_dist_traveled")),
                    )
                )
                if len(batch) >= 100000:
                    cur.executemany(
                        "INSERT INTO shapes VALUES (?,?,?,?,?)", batch
                    )
                    batch = []
            if batch:
                cur.executemany(
                    "INSERT INTO shapes VALUES (?,?,?,?,?)", batch
                )

        if "calendar_dates.txt" in archive.namelist():
            for row in reader("calendar_dates.txt"):
                cur.execute(
                    "INSERT INTO calendar_dates VALUES (?,?,?)",
                    (
                        row["service_id"],
                        row["date"],
                        int(row.get("exception_type", 1)),
                    ),
                )

    cur.executescript("""
    CREATE INDEX idx_routes_type ON routes(route_type);
    CREATE INDEX idx_routes_agency_line ON routes(agency_id, line);
    CREATE INDEX idx_routes_line ON routes(line);
    CREATE INDEX idx_trips_short_name ON trips(trip_short_name);
    CREATE INDEX idx_trips_realtime ON trips(realtime_trip_id);
    CREATE INDEX idx_trips_service ON trips(service_id);
    CREATE INDEX idx_trips_route ON trips(route_id);
    CREATE INDEX idx_trips_shape ON trips(shape_id);
    CREATE INDEX idx_stop_times_trip_seq ON stop_times(trip_id, stop_sequence);
    CREATE INDEX idx_stop_times_stop ON stop_times(stop_id);
    CREATE INDEX idx_stops_code ON stops(stop_code);
    CREATE INDEX idx_stops_latlon ON stops(lat, lon);
    CREATE INDEX idx_shapes_shape_seq ON shapes(shape_id, seq);
    CREATE INDEX idx_calendar_dates_service
        ON calendar_dates(service_id, date);
    """)
    con.commit()
    con.close()

    if os.path.exists(db_path):
        os.replace(db_path, db_path + ".pre_import.bak")
    os.replace(db_tmp, db_path)

    print(f"Built {db_path} in {time.time() - started:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a SQLite database from GTFS")
    parser.add_argument(
        "--input",
        default=os.environ.get("GTFS_ZIP", "./data/gtfs.zip"),
        help="GTFS zip archive",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("GTFS_DB", "./data/gtfs.db"),
        help="SQLite output file",
    )
    args = parser.parse_args()
    build_database(os.path.abspath(args.input), os.path.abspath(args.output))


if __name__ == "__main__":
    main()
