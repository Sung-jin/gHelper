#!/usr/bin/env python3
"""
1차 패턴 분석: 라벨링된 습격 구간 JSON에서 공통 hex 패턴 추출.
label/ 에서 실행. 데이터 경로: tools/analyze/
"""
import json
import os
from collections import Counter, defaultdict

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYZE_DIR = os.path.join(_THIS_DIR, "..", "analyze")
SKIP_EMPTY = True
PREFIX_LENS = [1, 2, 3, 4]
CHUNK_HEX_LEN = 8


def load_all_raid_payloads():
    records = []
    for root, _, files in os.walk(ANALYZE_DIR):
        for f in files:
            if not f.endswith(".json") or "INDEX" in f:
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except Exception:
                continue
            meta = data.get("meta", {})
            packets = data.get("packets", [])
            if SKIP_EMPTY and len(packets) == 0:
                continue
            for p in packets:
                d = p.get("d")
                if isinstance(d, str) and len(d) >= 4:
                    records.append((path, meta, d.lower()))
    return records


def main():
    records = load_all_raid_payloads()
    if not records:
        print("라벨링된 패킷이 없습니다.")
        return

    files_seen = set()
    for path, meta, _ in records:
        files_seen.add(path)
    total_packets = len(records)
    total_files = len(files_seen)

    print("=" * 60)
    print("1차 패턴 분석 (습격 라벨 데이터 기준)")
    print("=" * 60)
    print(f"총 라벨 파일(1분 구간) 수: {total_files}")
    print(f"총 패킷 수: {total_packets}")
    print()

    for n in PREFIX_LENS:
        hex_len = n * 2
        prefix_counter = Counter()
        for _, _, d in records:
            if len(d) >= hex_len:
                prefix_counter[d[:hex_len]] += 1
        print(f"[패킷 시작 {n}바이트] 상위 10개")
        for pref, cnt in prefix_counter.most_common(10):
            pct = 100.0 * cnt / total_packets
            print(f"  {pref}  {cnt}회 ({pct:.1f}%)")
        print()

    chunk_counter = Counter()
    for _, _, d in records:
        for i in range(0, len(d) - CHUNK_HEX_LEN + 1, 2):
            chunk_counter[d[i : i + CHUNK_HEX_LEN]] += 1
    print(f"[전체 패킷 내 {CHUNK_HEX_LEN//2}바이트 청크] 상위 20개")
    for chunk, cnt in chunk_counter.most_common(20):
        pct = 100.0 * cnt / total_packets
        print(f"  {chunk}  {cnt}회 ({pct:.1f}%)")
    print()

    file_contains = defaultdict(set)
    for path, _, d in records:
        for i in range(0, len(d) - CHUNK_HEX_LEN + 1, 2):
            file_contains[d[i : i + CHUNK_HEX_LEN]].add(path)
    common_in_files = [
        (chunk, len(files))
        for chunk, files in file_contains.items()
        if len(files) >= max(2, total_files * 0.5)
    ]
    common_in_files.sort(key=lambda x: -x[1])
    print(f"[총 {total_files}개 파일 중 절반 이상에 등장한 {CHUNK_HEX_LEN//2}바이트 청크]")
    for chunk, nfiles in common_in_files[:25]:
        pct = 100.0 * nfiles / total_files
        print(f"  {chunk}  {nfiles}개 파일 ({pct:.1f}%)")
    print()

    by_stage = defaultdict(list)
    for _, meta, d in records:
        stage = meta.get("stage", "?")
        by_stage[stage].append(d[:4] if len(d) >= 4 else d)
    raid_stages = {"pre5", "pre1", "start"}
    baseline_stages = {"pre6", "pre4", "pre3", "pre2", "post1"}
    print("[단계별 패킷 시작 2바이트 상위 3개]")
    for stage in ("pre6", "pre5", "pre4", "pre3", "pre2", "pre1", "start", "post1"):
        arr = by_stage.get(stage, [])
        if not arr:
            continue
        c = Counter(arr)
        print(f"  {stage}: {dict(c.most_common(3))}")
    print()

    raid_records = [(p, m, d) for p, m, d in records if m.get("stage") in raid_stages]
    base_records = [(p, m, d) for p, m, d in records if m.get("stage") in baseline_stages]
    if raid_records and base_records:
        raid_prefix = Counter(d[:4].lower() for _, _, d in raid_records if len(d) >= 4)
        base_prefix = Counter(d[:4].lower() for _, _, d in base_records if len(d) >= 4)
        n_raid, n_base = sum(raid_prefix.values()), sum(base_prefix.values())
        diff = []
        for pref in set(raid_prefix) | set(base_prefix):
            r_pct = 100.0 * raid_prefix[pref] / n_raid if n_raid else 0
            b_pct = 100.0 * base_prefix[pref] / n_base if n_base else 0
            if r_pct >= 0.1 or b_pct >= 0.1:
                diff.append((pref, r_pct - b_pct, r_pct, b_pct))
        diff.sort(key=lambda x: -x[1])
        print("[습격(pre5/pre1/start) vs 비교군(pre6/pre4/pre3/pre2/post1) — 습격에서 상대적으로 더 많이 나온 2바이트]")
        for pref, delta, r_pct, b_pct in diff[:15]:
            print(f"  {pref}  습격 {r_pct:.2f}% vs 비교군 {b_pct:.2f}% (차이 +{delta:.2f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
