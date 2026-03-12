#!/usr/bin/env python3
"""
습격 알림 OCR 감지 — 별도 프로세스로 온/오프 가능.

- 지정한 영역(또는 전체 화면)을 주기적으로 캡처·OCR.
- "습격" 등 키워드가 보이면 그 순간의 timestamp + OCR 텍스트 전체를
  트리거 JSON으로 저장. (나중에 패킷 버퍼 덤프 프로세스가 이 트리거를 보고 덤프 가능)
- 잠수/자리 비울 때만 켜서 사용하는 용도. 창 위치가 바뀌면 영역을 다시 잡아야 함.

의존성: pip install pillow pytesseract mss
        시스템에 Tesseract 설치 + 한글(kor) 데이터 필요.
        Windows: https://github.com/UB-Mannheim/tesseract/wiki 에서 설치 시 한글 선택.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def _get_base_dir() -> Path:
    """EXE로 실행 시 exe 위치, 그 외에는 이 스크립트 디렉터리."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _load_config() -> dict | None:
    """base_dir/raid_ocr_config.json 이 있으면 로드. 없으면 None."""
    path = _get_base_dir() / "raid_ocr_config.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_region_file() -> str:
    """pick_region으로 저장한 영역이 있으면 반환. 없으면 빈 문자열(전체 화면)."""
    path = _get_base_dir() / "raid_ocr_region.txt"
    if not path.is_file():
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def parse_region(s: str) -> tuple[int, int, int, int] | None:
    """'left,top,width,height' -> (left, top, width, height)."""
    if not s or not s.strip():
        return None
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        return None
    try:
        return tuple(int(x) for x in parts)
    except ValueError:
        return None


def capture_region(mss_obj, region: tuple[int, int, int, int] | None):
    """화면 영역 캡처. region=None 이면 전체 화면."""
    import mss
    if region is None:
        with mss_obj as sct:
            return sct.grab(sct.monitors[0])
    left, top, width, height = region
    with mss_obj as sct:
        return sct.grab({"left": left, "top": top, "width": width, "height": height})


def image_to_text(pil_image, lang: str = "kor+eng") -> str:
    """PIL Image -> OCR 텍스트."""
    import pytesseract
    return pytesseract.image_to_string(pil_image, lang=lang).strip()


def slug_from_ocr(text: str, max_len: int = 40) -> str:
    """OCR 텍스트에서 파일명에 쓸 수 있는 짧은 라벨 추출 (장소명 등)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "raid"
    raw = lines[0] if lines else "raid"
    cleaned = re.sub(r"[^\w\s가-힣]", "", raw).strip().replace(" ", "_")
    return (cleaned[:max_len] or "raid")[:max_len]


def stage_from_ocr(text: str) -> str:
    """
    OCR 텍스트에서 습격 단계 추출.
    같은 습격 = 5분 전, 1분 전, 지금 시작 3단계이므로, dedupe 시 (날짜, 장소, 단계)로 구분.
    """
    t = text.replace(" ", "")
    if "5분전" in t or "5분 전" in text:
        return "pre5"
    if "1분전" in t or "1분 전" in text:
        return "pre1"
    if "지금" in t or "시작" in t:
        return "start"
    return "unknown"


def place_slug_from_ocr(text: str, max_len: int = 30) -> str:
    """장소명만 추출 (5분 전/1분 전/시작 등 제거). dedupe 키용."""
    raw = re.sub(r"5분\s*전|1분\s*전|지금\s*시작|습격\s*", " ", text)
    raw = re.sub(r"[^\w\s가-힣]", "", raw).strip().replace(" ", "_")
    return (raw[:max_len] or "place")[:max_len].strip("_") or "place"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="주기적으로 화면 영역을 OCR하여 '습격' 키워드 감지 시 트리거 파일 저장.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="캡처 간격(초). 기본 1.0.",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="",
        help="캡처 영역: left,top,width,height (픽셀). 비우면 전체 화면.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="트리거 JSON 저장 폴더. 기본: 이 스크립트 기준 capture/triggers.",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default="습격",
        help="감지할 키워드. 기본: 습격.",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="kor+eng",
        help="Tesseract 언어. 기본: kor+eng.",
    )
    parser.add_argument(
        "--on-trigger-cmd",
        type=str,
        default="",
        help="습격 감지 시 실행할 명령 (선택). 예: 패킷 버퍼 덤프 스크립트.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="캡처·OCR만 하고 트리거 파일은 쓰지 않음.",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=5.0,
        help="같은 감지 연속 기록 방지 쿨다운(초). 기본 5.",
    )
    parser.add_argument(
        "--dedupe-day",
        action="store_true",
        default=True,
        help="같은 날 같은 장소·같은 단계(5분전/1분전/시작) 1회만 기록. 기본 on.",
    )
    parser.add_argument(
        "--no-dedupe-day",
        action="store_false",
        dest="dedupe_day",
        help="--dedupe-day 비활성화 (매번 기록).",
    )
    # 설정 파일(EXE와 같은 폴더의 raid_ocr_config.json) 우선 적용
    config = _load_config()
    if config:
        if "interval" in config:
            parser.set_defaults(interval=float(config["interval"]))
        if "region" in config:
            parser.set_defaults(region=str(config["region"]))
        if "output_dir" in config:
            parser.set_defaults(output_dir=str(config["output_dir"]))
        if "keyword" in config:
            parser.set_defaults(keyword=str(config["keyword"]))
        if "lang" in config:
            parser.set_defaults(lang=str(config["lang"]))
        if "cooldown" in config:
            parser.set_defaults(cooldown=float(config["cooldown"]))
        if "dedupe_day" in config:
            parser.set_defaults(dedupe_day=bool(config["dedupe_day"]))
        if "on_trigger_cmd" in config:
            parser.set_defaults(on_trigger_cmd=str(config.get("on_trigger_cmd", "")))
    elif getattr(sys, "frozen", False):
        # EXE이고 설정 파일 없을 때 기본 인터벌 60초
        parser.set_defaults(interval=60.0)

    args = parser.parse_args()

    # region: 인자 > config > raid_ocr_region.txt(pick_region 저장) > 비어있으면 전체 화면
    region_str = args.region.strip()
    if not region_str and config:
        region_str = (config.get("region") or "").strip()
    if not region_str:
        region_str = _load_region_file()
    region = parse_region(region_str)

    try:
        import mss
        import pytesseract
        from PIL import Image
    except ImportError as e:
        print("필요 패키지: pip install pillow pytesseract mss", file=sys.stderr)
        print(f"ImportError: {e}", file=sys.stderr)
        return 1
    out_dir = args.output_dir.strip()
    if not out_dir:
        out_dir = str(_get_base_dir() / "triggers")
    os.makedirs(out_dir, exist_ok=True)

    keyword = args.keyword.strip()
    if not keyword:
        print("--keyword 를 비울 수 없습니다.", file=sys.stderr)
        return 1

    interval = max(0.3, args.interval)
    last_trigger_time: float = 0
    cooldown_sec = max(0.0, args.cooldown)
    dedupe_day = args.dedupe_day
    dedupe_file = os.path.join(out_dir, ".dedupe_day.json")  # { "date": "YYYYMMDD", "keys": ["장소|pre5", ...] }

    def _dedupe_key(place: str, stage: str) -> str:
        return f"{place}|{stage}"

    def already_triggered_today(place_slug: str, stage: str) -> bool:
        if not dedupe_day:
            return False
        today = datetime.now().strftime("%Y%m%d")
        key = _dedupe_key(place_slug, stage)
        try:
            if os.path.exists(dedupe_file):
                with open(dedupe_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == today and key in data.get("keys", []):
                    return True
        except Exception:
            pass
        return False

    def mark_triggered_today(place_slug: str, stage: str) -> None:
        if not dedupe_day:
            return
        today = datetime.now().strftime("%Y%m%d")
        key = _dedupe_key(place_slug, stage)
        try:
            data = {"date": today, "keys": []}
            if os.path.exists(dedupe_file):
                with open(dedupe_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            if data.get("date") != today:
                data = {"date": today, "keys": []}
            if key not in data["keys"]:
                data["keys"].append(key)
            with open(dedupe_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    print(f"[raid_ocr] 시작. 영역: {'전체' if region is None else region}, 간격: {interval}초, 키워드: {keyword!r}")
    print(f"[raid_ocr] 트리거 저장: {out_dir}, 쿨다운: {cooldown_sec}초, 같은날 같은장소·같은단계 1회: {dedupe_day}")
    if args.on_trigger_cmd:
        print(f"[raid_ocr] 감지 시 실행: {args.on_trigger_cmd}")
    print("종료: Ctrl+C")

    mss_obj = mss.mss()

    try:
        while True:
            try:
                shot = capture_region(mss_obj, region)
                # mss: BGRA -> PIL RGB
                img = Image.frombytes(
                    "RGB",
                    (shot.width, shot.height),
                    shot.bgra,
                    "raw",
                    "BGRX",
                )
                text = image_to_text(img, lang=args.lang)
            except Exception as e:
                print(f"[!] 캡처/OCR 오류: {e}", file=sys.stderr)
                time.sleep(interval)
                continue

            if keyword in text:
                try:
                    now = time.time()
                    if now - last_trigger_time < cooldown_sec:
                        time.sleep(interval)
                        continue
                    label = slug_from_ocr(text)
                    place_slug = place_slug_from_ocr(text)
                    stage = stage_from_ocr(text)
                    if already_triggered_today(place_slug, stage):
                        time.sleep(interval)
                        continue
                    last_trigger_time = now

                    ts = datetime.now()
                    ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%S")
                    ts_file = ts.strftime("%Y%m%d_%H%M%S")

                    payload = {
                        "timestamp": ts_iso,
                        "timestamp_file": ts_file,
                        "keyword": keyword,
                        "ocr_text": text,
                        "label_slug": label,
                        "place_slug": place_slug,
                        "stage": stage,
                    }

                    if not args.dry_run:
                        mark_triggered_today(place_slug, stage)
                        # 파일명에 사용할 수 없는 문자 방지 (장소 없이 '습격 발생' 등만 있을 때도 안전)
                        safe_label = re.sub(r'[<>:"/\\|?*]', "_", label).strip() or "raid"
                        fname = f"raid_trigger_{ts_file}_{safe_label}.json"
                        out_path = os.path.join(out_dir, fname)
                        with open(out_path, "w", encoding="utf-8") as f:
                            json.dump(payload, f, ensure_ascii=False, indent=2)
                        print(f"[+] 트리거 저장: {out_path}")

                        if args.on_trigger_cmd.strip():
                            try:
                                subprocess.run(
                                    args.on_trigger_cmd,
                                    shell=True,
                                    cwd=str(_get_base_dir()),
                                    timeout=30,
                                )
                            except Exception as e:
                                print(f"[!] on-trigger 명령 오류: {e}", file=sys.stderr)
                    else:
                        print(f"[dry-run] 감지: {ts_iso} | {label!r}")
                except Exception as e:
                    # 채팅 '습격 발생했어' 등 장소/단계 없거나 예상 못 한 OCR이라도 프로세스는 유지
                    print(f"[!] 트리거 처리 중 오류 (계속 실행): {e}", file=sys.stderr)

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[raid_ocr] 종료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
