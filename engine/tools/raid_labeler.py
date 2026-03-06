import argparse
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any


def slug(name: str) -> str:
    """파일명에 쓸 수 있는 짧은 식별자 (area_name 참고용)."""
    s = name.strip().replace(" ", "_")
    return re.sub(r"[^\w\-]", "_", s)[:32]


def parse_events(spec: str) -> List[Dict[str, str]]:
    """
    Parse event spec string into a list of {hh, mm, stage}.
    Format examples:
      "22:47=pre5,22:51=pre1,22:52=start"
      "2235=start"  (hhmm without colon)
    """
    events: List[Dict[str, str]] = []
    if not spec:
        return events

    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue

        if "=" in part:
            hhmm, stage = part.split("=", 1)
        else:
            hhmm, stage = part, "unknown"

        hhmm = hhmm.strip()
        stage = stage.strip()

        if ":" in hhmm:
            hh, mm = hhmm.split(":", 1)
        else:
            # assume 4-digit HHMM
            if len(hhmm) != 4:
                raise ValueError(f"Invalid time format in events spec: {hhmm}")
            hh, mm = hhmm[:2], hhmm[2:]

        events.append({"hh": hh, "mm": mm, "stage": stage})

    return events


def filter_packets_by_minute(
    packets: List[Dict[str, Any]], hh: str, mm: str
) -> List[Dict[str, Any]]:
    """Return packets where t starts with 'HH:MM:'."""
    prefix = f"{hh}:{mm}:"
    result: List[Dict[str, Any]] = []

    for p in packets:
        if not isinstance(p, dict):
            continue
        t = p.get("t")
        if isinstance(t, str) and t.startswith(prefix):
            result.append(p)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract labelled raid sample windows from packet recording JSON."
    )
    parser.add_argument("--input", required=True, help="Input packet JSON file path")
    parser.add_argument("--date", required=True, help="Date string, e.g. 20260305")
    parser.add_argument(
        "--area-name", required=True, help="Location name (e.g. 외국 기업지구 하부)"
    )
    parser.add_argument(
        "--events",
        required=True,
        help='Comma-separated list of events, e.g. "22:47=pre5,22:51=pre1,22:52=start"',
    )

    args = parser.parse_args()

    input_path = args.input
    date_str = args.date
    area_name = args.area_name
    events_spec = args.events

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Input JSON must be a list of {t, d} objects.")

    events = parse_events(events_spec)

    base_dir = os.path.join(os.path.dirname(__file__), "analyze", date_str)
    os.makedirs(base_dir, exist_ok=True)

    generated_at = datetime.now().isoformat(timespec="seconds")

    for ev in events:
        hh = ev["hh"]
        mm = ev["mm"]
        stage = ev["stage"]

        packets = filter_packets_by_minute(data, hh, mm)

        out_doc = {
            "meta": {
                "date": date_str,
                "area_name": area_name,
                "stage": stage,
                "minute": f"{hh}:{mm}",
                "generated_at": generated_at,
                "window": "minute",  # 1-minute window
            },
            "packets": packets,
        }

        filename = f"{hh}{mm}_{slug(area_name)}_{stage}.json"
        out_path = os.path.join(base_dir, filename)

        with open(out_path, "w", encoding="utf-8") as out_f:
            json.dump(out_doc, out_f, ensure_ascii=False, indent=2)

        print(f"Wrote {out_path} ({len(packets)} packets)")


if __name__ == "__main__":
    main()

