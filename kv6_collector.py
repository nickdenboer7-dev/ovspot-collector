#!/usr/bin/env python3
"""Standalone NDOV KV6 collector.

Reads gzip-compressed KV6 messages from an NDOV ZeroMQ PUB/SUB endpoint,
converts RD New coordinates to WGS84 and writes a compact JSON snapshot.

This public version intentionally contains no OVspot web, renderer, admin,
database, analytics, or private runtime integrations.
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import zmq

ZMQ_URL = os.environ.get(
    "KV6_ZMQ_URL",
    "tcp://pubsub.besteffort.ndovloket.nl:7658",
)
OUTPUT_FILE = Path(os.environ.get("KV6_OUTPUT_FILE", "./data/kv6_vehicles.json"))
VEHICLE_TIMEOUT = int(os.environ.get("KV6_VEHICLE_TIMEOUT", "180"))
SAVE_INTERVAL = float(os.environ.get("KV6_SAVE_INTERVAL", "5"))
SUBSCRIBE_PREFIX = os.environ.get("KV6_SUBSCRIBE_PREFIX", "/")
RECEIVE_HWM = int(os.environ.get("KV6_RECEIVE_HWM", "10000"))

vehicles: dict[str, dict] = {}


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rd_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convert Dutch RD New coordinates to WGS84."""
    dx = (x - 155000.0) / 100000.0
    dy = (y - 463000.0) / 100000.0

    lat = 52.15517440 + (
        3235.65389 * dy
        - 32.58297 * dx**2
        - 0.24750 * dy**2
        - 0.84978 * dx**2 * dy
        - 0.06550 * dy**3
        - 0.01709 * dx**2 * dy**2
        - 0.00738 * dx
        + 0.00530 * dx**4
        - 0.00039 * dx**2 * dy**3
        + 0.00033 * dx**4 * dy
        - 0.00012 * dx * dy
    ) / 3600.0

    lon = 5.38720621 + (
        5260.52916 * dx
        + 105.94684 * dx * dy
        + 2.45656 * dx * dy**2
        - 0.81885 * dx**3
        + 0.05594 * dx * dy**3
        - 0.05607 * dx**3 * dy
        + 0.01199 * dy
        - 0.00256 * dx**3 * dy**2
        + 0.00128 * dx * dy**4
        + 0.00022 * dy**2
        - 0.00022 * dx**2
        + 0.00026 * dx**5
    ) / 3600.0

    return lat, lon


def record_fields(element: ET.Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    for child in element.iter():
        if child is element or not child.text:
            continue
        name = localname(child.tag).lower()
        value = child.text.strip()
        if value and name not in fields:
            fields[name] = value
    return fields


def parse_kv6(xml_data: bytes, topic: str) -> int:
    """Parse one KV6 payload and update the in-memory vehicle snapshot."""
    root = ET.fromstring(xml_data)
    topic_parts = topic.strip("/").split("/")
    topic_carrier = topic_parts[0].upper() if topic_parts else "UNKNOWN"
    count = 0

    for element in root.iter():
        record_type = localname(element.tag).upper()
        if record_type not in {
            "ONROUTE", "ARRIVAL", "DEPARTURE", "ONSTOP", "OFFROUTE", "INIT"
        }:
            continue

        fields = record_fields(element)
        rd_x = to_float(fields.get("rd-x"))
        rd_y = to_float(fields.get("rd-y"))
        if rd_x is None or rd_y is None or rd_x == 0 or rd_y == 0:
            continue

        lat, lon = rd_to_wgs84(rd_x, rd_y)
        if not (50.5 <= lat <= 54.0 and 3.0 <= lon <= 8.0):
            continue

        operator = fields.get("dataownercode") or topic_carrier
        line = fields.get("lineplanningnumber") or ""
        journey = fields.get("journeynumber") or ""
        reinforcement = fields.get("reinforcementnumber") or "0"
        vehicle_number = fields.get("vehiclenumber") or ""

        vehicle_id = (
            f"{operator}_{vehicle_number}"
            if vehicle_number
            else f"{operator}_{line}_{journey}_{reinforcement}"
        )

        vehicles[vehicle_id] = {
            "vehicle_id": vehicle_id,
            "operator": operator,
            "line_planning_number": line,
            "journey_number": journey,
            "reinforcement_number": reinforcement,
            "vehicle_number": vehicle_number,
            "record_type": record_type,
            "offroute": record_type == "OFFROUTE",
            "lat": lat,
            "lon": lon,
            "rd_x": rd_x,
            "rd_y": rd_y,
            "stop_code": fields.get("userstopcode") or "",
            "passage_sequence_number": fields.get("passagesequencenumber"),
            "punctuality": fields.get("punctuality") or "",
            "distance_since_stop": fields.get("distancesincelastuserstop") or "",
            "kv6_timestamp": fields.get("timestamp") or "",
            "number_of_coaches": fields.get("numberofcoaches") or "",
            "updated": int(time.time()),
        }
        count += 1

    return count


def cleanup() -> None:
    cutoff = int(time.time()) - VEHICLE_TIMEOUT
    for vehicle_id in [
        key for key, value in vehicles.items()
        if int(value.get("updated", 0)) < cutoff
    ]:
        del vehicles[vehicle_id]


def write_snapshot() -> None:
    cleanup()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": int(time.time()),
        "vehicle_count": len(vehicles),
        "vehicles": list(vehicles.values()),
    }
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{OUTPUT_FILE.name}.",
        dir=str(OUTPUT_FILE.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, OUTPUT_FILE)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> None:
    context = zmq.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.RCVHWM, RECEIVE_HWM)
    subscriber.connect(ZMQ_URL)
    subscriber.setsockopt_string(zmq.SUBSCRIBE, SUBSCRIBE_PREFIX)

    print(f"Connected to {ZMQ_URL}")
    print(f"Writing snapshots to {OUTPUT_FILE}")

    last_save = 0.0
    message_count = 0

    try:
        while True:
            parts = subscriber.recv_multipart()
            if len(parts) < 2:
                continue

            topic = parts[0].decode("utf-8", errors="ignore")
            if "KV6posinfo" not in topic:
                continue

            try:
                xml_data = gzip.GzipFile(
                    fileobj=BytesIO(b"".join(parts[1:]))
                ).read()
                added = parse_kv6(xml_data, topic)
            except (OSError, ET.ParseError, ValueError) as exc:
                print(f"Skipping invalid message on {topic}: {exc}")
                continue

            message_count += 1
            now = time.monotonic()
            if now - last_save >= SAVE_INTERVAL:
                write_snapshot()
                print(
                    f"vehicles={len(vehicles)} "
                    f"messages={message_count} records={added}"
                )
                last_save = now
    except KeyboardInterrupt:
        print("Stopping collector")
    finally:
        write_snapshot()
        subscriber.close()
        context.term()


if __name__ == "__main__":
    main()
