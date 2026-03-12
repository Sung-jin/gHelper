#!/usr/bin/env python3
"""
기존 라벨링된 습격에 대해 주변 구간(pre6, pre4, pre3, pre2, post1)을 추가 추출하는 배치.
label/ 에서 실행. raid_labeler 는 tools/analyze/ 에 출력.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LABEL_DIR = Path(__file__).resolve().parent
RUN_CWD = LABEL_DIR.parent  # engine/tools (analyze/ 가 있는 곳)
sys.path.insert(0, str(LABEL_DIR))

from raid_labeler import (
    expand_events_with_surrounding,
    parse_events,
)


RAIDS = [
    ("20260305", "외국 기업지구 하부", "22:47=pre5,22:51=pre1,22:52=start"),
    ("20260305", "체험 농장 하부", "23:35=pre5,23:39=pre1,23:40=start"),
    ("20260306", "외국 기업지구 하부", "22:43=pre5,22:47=pre1,22:48=start"),
    ("20260306", "체험 농장 하부", "23:31=pre5,23:35=pre1,23:36=start"),
    ("20260307", "산책로 굽은길", "00:29=pre5,00:33=pre1,00:34=start"),
    ("20260307", "농업보호구역 농장 폐허", "20:11=pre5,20:15=pre1,20:16=start"),
    ("20260307", "농업진흥구역 경작지", "20:48=pre5,20:52=pre1,20:53=start"),
    ("20260307", "산책로 두물경", "23:11=pre5,23:15=pre1,23:16=start"),
    ("20260307", "복합지구 상부 공장", "23:57=pre5"),
    ("20260308", "복합지구 상부 공장", "00:01=pre1,00:02=start"),
    ("20260309", "깊은 산길 개미군락", "00:16=pre5,00:20=pre1,00:21=start"),
    ("20260309", "서쪽 산길 폐허", "00:51=pre5,00:55=pre1,00:56=start"),
    ("20260309", "서쪽 산길 아라크니아", "20:02=pre5,20:05=pre1,20:07=start"),
    ("20260309", "산책로 두물경", "20:27=pre5,20:31=pre1,20:32=start"),
    ("20260309", "산책로 중앙", "22:41=pre5,22:45=pre1,22:46=start"),
    ("20260310", "농업진흥구역 경작지", "00:01=pre5,00:05=pre1,00:06=start"),
    ("20260310", "과수원 중앙", "00:20=pre5,00:24=pre1,00:25=start"),
]


def _file_suffix_for_minute(hh: str, mm: str) -> str:
    mm_int = int(mm)
    base_mm = (mm_int // 10) * 10
    return f"{hh}{base_mm:02d}"


def _events_to_spec(events: list[dict]) -> str:
    return ",".join(f"{e['hh']}:{e['mm']}={e['stage']}" for e in events)


def group_events_by_file(events: list[dict]) -> dict[str, list[dict]]:
    by_file: dict[str, list[dict]] = {}
    for ev in events:
        key = _file_suffix_for_minute(ev["hh"], ev["mm"])
        by_file.setdefault(key, []).append(ev)
    for key in by_file:
        by_file[key].sort(key=lambda e: (e["hh"], e["mm"]))
    return by_file


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Expand raid labels with surrounding minutes (pre6, pre4, pre3, pre2, post1).")
    parser.add_argument("--packet-dir", default=os.environ.get("PACKET_DIR"), help="Directory containing packet_YYYYMMDD_HHMM.json (or set PACKET_DIR)")
    parser.add_argument("--dry-run", action="store_true", help="Only print commands, do not run.")
    args = parser.parse_args()

    packet_dir = Path(args.packet_dir) if args.packet_dir else None
    dry_run = args.dry_run

    if not dry_run and (not packet_dir or not packet_dir.is_dir()):
        print("Usage: PACKET_DIR=/path/to/packets python expand_raid_labels_batch.py")
        print("   or: python expand_raid_labels_batch.py --packet-dir /path")
        print("   or: python expand_raid_labels_batch.py --dry-run  # print commands only")
        if args.packet_dir:
            print(f"Error: not a directory: {args.packet_dir}")
        sys.exit(1)

    labeler = LABEL_DIR / "raid_labeler.py"
    ran = 0
    skipped = 0

    for date_str, area_name, events_spec in RAIDS:
        events = parse_events(events_spec)
        expanded = expand_events_with_surrounding(events)
        if not expanded:
            continue
        by_file = group_events_by_file(expanded)

        for file_suffix, file_events in by_file.items():
            if not file_events:
                continue
            spec = _events_to_spec(file_events)
            input_path = packet_dir / f"packet_{date_str}_{file_suffix}.json" if packet_dir else None

            if dry_run:
                inp = input_path or f"<packet_dir>/packet_{date_str}_{file_suffix}.json"
                print(f"python {labeler} --input {inp} --date {date_str} --area-name {area_name!r} --events {spec!r}")
                ran += 1
                continue

            if not input_path or not input_path.is_file():
                print(f"Skip (file not found): {input_path}", file=sys.stderr)
                skipped += 1
                continue

            cmd = [
                sys.executable,
                str(labeler),
                "--input", str(input_path),
                "--date", date_str,
                "--area-name", area_name,
                "--events", spec,
            ]
            subprocess.run(cmd, cwd=str(RUN_CWD))
            ran += 1

    if not dry_run:
        print(f"Done. Ran {ran}, skipped {skipped}.", file=sys.stderr)
    else:
        print(f"# Would run {ran} labeler invocations (set PACKET_DIR and re-run without --dry-run).", file=sys.stderr)


if __name__ == "__main__":
    main()
