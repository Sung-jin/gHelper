# 습격 OCR 캡처 (RaidOcr)

- **기본**: 캡처 영역은 **전체 화면**. 좌표를 몰라도 됨. cooldown + dedupe_day 로 같은 이벤트는 한 번만 기록.
- **영역 제한**: PickRegion 실행 후 드래그로 영역 선택 → `raid_ocr_region.txt`에 저장됨. 다음 RaidOcr 실행부터 해당 영역만 캡처. 다시 전체 화면 쓰려면 `raid_ocr_region.txt` 삭제.
- **설정**: exe와 같은 폴더에 `raid_ocr_config.json` (선택). 없으면 기본값(예: 60초 간격). `raid_ocr_config.example.json` 참고.
- **오탐(채팅 "습격 발생했어" 등)**: 장소/단계를 못 찾아도 트리거 파일은 생성되고(place_slug/stage는 place·unknown 등). 예외 나도 프로세스는 종료되지 않고 계속 실행. 불필요한 파일은 나중에 히스토리에서 삭제하면 됨.
