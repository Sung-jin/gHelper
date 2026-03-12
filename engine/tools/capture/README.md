# 습격 OCR 캡처 (RaidOcr)

- **실행 환경**: GitHub Actions에서 `requirements.txt` 기준으로 의존성 설치 후 PyInstaller로 EXE 빌드. **사용자는 Python/pip 설치 없이** Actions에서 받은 RaidOcr.exe만 실행하면 됨. (analyzer와 동일하게 빌드 시점에 패키지가 EXE에 포함됨.)
- **사용자 PC에 필요한 것**: **Tesseract OCR만** 설치 (한글 데이터 포함). [다운로드](https://github.com/UB-Mannheim/tesseract/wiki) 후 설치하면 되고, 경로를 못 찾으면 `raid_ocr_config.json`에 `tesseract_cmd` 로 지정.
- **기본**: 캡처 영역은 **전체 화면**. cooldown + dedupe_day 로 같은 이벤트는 한 번만 기록.
- **영역 제한**: PickRegion 실행 후 드래그로 영역 선택 → `raid_ocr_region.txt` 저장. 다시 전체 화면은 해당 파일 삭제.
- **설정**: exe와 같은 폴더에 `raid_ocr_config.json` (선택). `raid_ocr_config.example.json` 참고. `tesseract_cmd` 로 Tesseract 경로 지정 가능.
- **오탐**: 채팅 "습격 발생했어" 등은 트리거 파일은 생성되고, 예외 나도 프로세스는 계속 실행. 불필요한 파일은 나중에 삭제하면 됨.
