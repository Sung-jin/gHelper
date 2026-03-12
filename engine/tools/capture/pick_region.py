#!/usr/bin/env python3
"""
캡처할 화면 영역을 드래그로 지정. 선택이 끝나면 left,top,width,height 를 출력하고,
이 스크립트와 같은 폴더에 raid_ocr_region.txt 로 저장함. RaidOcr 실행 시 자동으로 이 영역 사용.

전체 화면을 쓰려면 raid_ocr_region.txt 를 지우면 됨.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


try:
    import tkinter as tk
    from tkinter import font as tkfont
except ImportError:
    print("tkinter 가 필요합니다. (보통 Python 기본 포함)", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.3)
    root.configure(bg="black")
    root.attributes("-topmost", True)

    canvas = tk.Canvas(root, cursor="cross", bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    start_xy: list[int] = []
    rect_id: str | None = None

    def on_press(e):
        nonlocal rect_id
        start_xy[:] = [e.x, e.y]
        if rect_id:
            canvas.delete(rect_id)
        rect_id = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="lime", width=2)

    def on_drag(e):
        if not start_xy or not rect_id:
            return
        canvas.coords(rect_id, start_xy[0], start_xy[1], e.x, e.y)

    def on_release(e):
        if not start_xy:
            return
        x1, y1 = start_xy[0], start_xy[1]
        x2, y2 = e.x, e.y
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width < 10 or height < 10:
            root.destroy()
            print("영역이 너무 작습니다. 다시 실행해 드래그로 넉넉히 잡아 주세요.", file=sys.stderr)
            return
        region = f"{left},{top},{width},{height}"
        base = _get_base_dir()
        region_file = base / "raid_ocr_region.txt"
        try:
            region_file.write_text(region, encoding="utf-8")
            print(region)
            print(f"\n영역을 저장했습니다: {region_file}", file=sys.stderr)
            print("RaidOcr 실행 시 이 영역이 자동 적용됩니다. 전체 화면으로 쓰려면 이 파일을 지우세요.", file=sys.stderr)
        except Exception as e:
            print(region)
            print(f"\n파일 저장 실패: {e}\n위 좌표를 raid_ocr.py --region 에 넣어 사용하세요.", file=sys.stderr)
        root.destroy()
        return 0

    def on_escape(e):
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    # 안내 문구
    guide = tk.Label(
        root,
        text="캡처할 영역을 마우스로 드래그하세요. (Esc: 취소)",
        fg="white",
        bg="black",
        font=tkfont.Font(size=14),
    )
    guide.place(relx=0.5, rely=0.02, anchor=tk.N)

    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
