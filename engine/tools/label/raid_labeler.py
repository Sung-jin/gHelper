# 라벨링 전용. 출력 경로: tools/analyze/YYYYMMdd/
import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# analyze 디렉터리는 label/ 상위(tools/analyze)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ANALYZE_BASE = os.path.join(_THIS_DIR, "..", "analyze")


def slug(name: str) -> str:
    """파일명에 쓸 수 있는 짧은 식별자 (area_name 참고용)."""
    s = name.strip().replace(" ", "_")
    return re.sub(r"[^\w\-]", "_", s)[:32]


def _to_min(hh: str, mm: str) -> int:
    return int(hh) * 60 + int(mm)


def _from_min(m: int) -> tuple:
    m = m % (24 * 60)
    return f"{m // 60:02d}", f"{m % 60:02d}"


def expand_events_with_surrounding(events: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Given events that include pre5, pre1, start, add pre6, pre4, pre3, pre2, post1
    so we have comparison baseline (비교군) and post (직후) for analysis.
    """
    by_stage = {ev["stage"]: ev for ev in events}
    pre5 = by_stage.get("pre5")
    pre1 = by_stage.get("pre1")
    start_ev = by_stage.get("start")
    existing_minutes = {(_to_min(e["hh"], e["mm"])) for e in events}

    added: List[Dict[str, str]] = []
    if pre5:
        m5 = _to_min(pre5["hh"], pre5["mm"])
        for delta, stage in [(-1, "pre6"), (1, "pre4"), (2, "pre3")]:
            m = m5 + delta
            if 0 <= m < 24 * 60 and m not in existing_minutes:
                hh, mm = _from_min(m)
                added.append({"hh": hh, "mm": mm, "stage": stage})
                existing_minutes.add(m)
    if pre1:
        m1 = _to_min(pre1["hh"], pre1["mm"])
        m = m1 - 1  # pre2
        if 0 <= m < 24 * 60 and m not in existing_minutes:
            hh, mm = _from_min(m)
            added.append({"hh": hh, "mm": mm, "stage": "pre2"})
            existing_minutes.add(m)
    if start_ev:
        m0 = _to_min(start_ev["hh"], start_ev["mm"])
        m = m0 + 1  # post1
        if 0 <= m < 24 * 60 and m not in existing_minutes:
            hh, mm = _from_min(m)
            added.append({"hh": hh, "mm": mm, "stage": "post1"})
            existing_minutes.add(m)

    out = events + added
    out.sort(key=lambda e: (_to_min(e["hh"], e["mm"])))
    return out


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


def infer_time_range_from_packets(packets: List[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
    """
    패킷의 t 필드에서 시각 범위(분 단위) 추론.
    시작 시각 기준 10분 파일 등에서 실제 포함 구간을 알 때 사용.
    Returns (minute_start, minute_end) inclusive, 또는 None.
    """
    minutes: list[int] = []
    for p in packets:
        if not isinstance(p, dict):
            continue
        t = p.get("t")
        if not isinstance(t, str) or len(t) < 5:
            continue
        # "HH:MM:SS.xxx" -> HH*60+MM
        parts = t.split(":")
        if len(parts) >= 2:
            try:
                hh, mm = int(parts[0]), int(parts[1][:2])
                minutes.append(hh * 60 + mm)
            except ValueError:
                continue
    if not minutes:
        return None
    return min(minutes), max(minutes)


def filter_events_in_range(
    events: List[Dict[str, str]], min_minute: int, max_minute: int
) -> List[Dict[str, str]]:
    """이벤트 중 (hh, mm)이 [min_minute, max_minute] 안에 있는 것만 반환."""
    result = []
    for ev in events:
        m = _to_min(ev["hh"], ev["mm"])
        if min_minute <= m <= max_minute:
            result.append(ev)
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
    parser.add_argument(
        "--expand-surrounding",
        action="store_true",
        help="Add pre6, pre4, pre3, pre2, post1 for comparison baseline and post-raid.",
    )
    parser.add_argument(
        "--events-only-in-range",
        action="store_true",
        help="Start-time-based 10min file: infer time range from packet 't', extract only events within that range.",
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
    if args.expand_surrounding:
        events = expand_events_with_surrounding(events)

    if args.events_only_in_range:
        rng = infer_time_range_from_packets(data)
        if rng:
            min_m, max_m = rng
            events = filter_events_in_range(events, min_m, max_m)
            print(f"# Time range in file: {_from_min(min_m)[0]}:{_from_min(min_m)[1]} ~ {_from_min(max_m)[0]}:{_from_min(max_m)[1]} → {len(events)} events in range", file=sys.stderr)
        if not events:
            print("No events fall within the file's time range. Check file content or omit --events-only-in-range.", file=sys.stderr)
            return

    base_dir = os.path.join(_ANALYZE_BASE, date_str)
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
