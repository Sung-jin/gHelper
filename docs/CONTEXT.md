# gHelper 프로젝트 컨텍스트

> 요구사항, 방향성, 워크플로, 해야 할 일을 한 문서로 유지. (다른 환경에서 열어도 컨텍스트 유지용)

---

## 1. 프로젝트 목표와 방향성

### 1.1 현재
- **특정 프로세스(이터널시티 클라이언트)의 패킷**을 모니터링해서, **습격(레이드) 관련 패킷**이 오면 **Discord로 알림**을 보내는 기능.
- 습격 패킷을 **어떤 규칙으로 구분할지**는 아직 확정되지 않음 → **패킷 데이터를 쌓고, 패턴을 처음부터 파악**하는 중.

### 1.2 장기
- 게임만이 아니라 **OCR, 원격 부팅, 원격 게임 로그인** 등 개인용 유틸/헬퍼를 추가해 **개인용 도구 모음**으로 확장.
- **Electron**으로 크로스플랫폼 앱 제공 예정.
- 지금은 **engine/tools** 하위(패킷 분석·라벨링)에만 집중.

### 1.3 참고
- **이터널시티**: 다중 클라이언트 가능. 습격 메시지는 **클라이언트 수만큼** 올 수 있음(고정 아님).
- **mapping.json**: 참고용일 뿐. **신뢰하지 말 것.** 80a0, 8080, f180 같은 키도 믿지 말고, 패킷/유형은 **처음부터 다시 파악**.

---

## 2. 요구사항 요약

| 구분 | 내용 |
|------|------|
| 패킷 수집 | recording.py로 특정 프로세스 패킷 저장. **고정 10분 구간** 기준: `hh:00~hh:10`, `hh:10~hh:20`, … `hh:50~(hh+1):00`. 파일명 `packet_YYYYMMDD_HHMM.json` (예: `packet_20260305_2240.json` = 22:40~22:50). 실행 시점과 무관하게 구간만 보면 됨. |
| 습격 판별 | 방식 미정. analyzer.py는 **완전 새로 작성** 예정. 기존 1d00 가정 등 전부 제거. |
| Discord 알림 | 습격 감지 시 Webhook으로 알림. (utils.Notifier) |
| 라벨링 | 사용자가 "hh시 mm분/mm분/mm분 → ○○ 습격 (5분 전, 1분 전, 시작)" 알려주면, **해당 1분 전체** 패킷을 추출해 `engine/tools/analyze/YYYYMMdd/` 에 라벨과 함께 저장. |

---

## 3. 라벨링 워크플로

### 3.1 사용자 입력
- 예: `22시 47/51/52분 → 외국 기업지구 하부` (순서: 5분 전 → 1분 전 → 시작)
- 해당 날짜의 packet JSON 파일 경로.

### 3.2 AI(또는 실행 환경)가 할 일
1. **분석**: 해당 시각 전후 패킷에서 반복/특이점 간단 정리.
2. **추출**: 각 시각의 **해당 분 전체**(00초~59초) 레코드를 원본 JSON에서 추출.
3. **저장**: `engine/tools/analyze/YYYYMMdd/` 아래에 파일 생성.

### 3.3 저장 형식
- **파일명**: `HHMM_{area_name_slug}_{stage}.json` (예: `2247_외국_기업지구_하부_pre5.json`).
- **meta** (참고만, 신뢰용 아님):
  - `date`, `area_name`, `stage`(pre5/pre1/start), `minute`, `generated_at`, `window`
  - **넣지 않음**: `source_file`, `area_id` (mapping 기반 ID는 사용하지 않음).
- **packets**: 해당 1분의 `{ "t", "d" }` 배열 전체.

### 3.4 주변 구간·비교군
- 습격 구간(pre5/pre1/start)만 쓰면 **비습격 비교군**이 없어 "습격만의 시그니처" 검증이 어렵다.
- **주변 구간까지 라벨링**하면 같은 이벤트 전후로 **비교군(비습격)·원본(습격)·직후**가 같이 쌓여, 나중 분석·백데이터로 활용 가능.
- **추가 stage**: `pre6`, `pre4`, `pre3`, `pre2`(비교용), `post1`(직후).  
  예: 22:43=pre5, 22:47=pre1, 22:48=start → 22:42=pre6, 22:44=pre4, 22:45=pre3, 22:46=pre2, 22:49=post1 도 추출.
- **engine/tools/label/raid_labeler.py**: `--expand-surrounding` 시 위 구간을 자동 추가.
- **기존 라벨에 적용**: `engine/tools/label/expand_raid_labels_batch.py`로 이미 라벨된 습격에 대해 주변 구간을 일괄 추출.  
  `PACKET_DIR=/path python engine/tools/label/expand_raid_labels_batch.py` (패킷 디렉터리 없으면 `--dry-run`으로 명령만 출력).

### 3.5 도구
- **engine/tools/label/raid_labeler.py**: `--input`, `--date`, `--area-name`, `--events` (선택: `--expand-surrounding`).
- **engine/tools/label/expand_raid_labels_batch.py**: 기존 습격 목록에 대해 주변 구간까지 일괄 추출.
- Python 없는 환경에서는 “어디를 뽑을지”만 정리해 주고, 개발 가능한 환경에서 한 번에 실행 가능.

---

## 4. analyze/ 데이터와 Git

- **tools/analyze/** 아래 JSON은 **라벨링된 샘플(백데이터)**.
- **다른 환경에서 작업할 계획이 없다면** GitHub에 올리지 않아도 됨. 로컬/백업만 해도 충분.
- 올리면: 레포 크기 증가, 패킷 덤프가 포함되므로 **비공개 레포**라도 신경 쓸 수 있음.
- **권장**: `engine/tools/analyze/` 를 `.gitignore`에 넣고, **코드 + 이 컨텍스트 문서만** GitHub에 관리. 샘플은 로컬/별도 백업.
- 나중에 다른 PC에서 “같은 샘플로 분석 이어가기”가 필요하면, 그때 analyze/ 만 선택적으로 동기화(클라우드, USB 등)하면 됨.

---

## 5. 해야 할 일 / 진행 상황

### 5.1 지금
- [x] 라벨링 워크플로 정립 (1분 추출, meta 규칙, raid_labeler.py).
- [x] 2026-03-05 습격 2건 추출 (외국 기업지구 하부, 체험 농장 하부).
- [ ] **습격 데이터 계속 수집** (Windows에서 쌓아 두었다가, 개발 환경에서 한 번에 라벨링 요청 예정).

### 5.2 이후
- 기존 라벨에 **주변 구간 추가** 후 **패턴 분석 재실행**: 비교군(pre6/pre4/pre2 등) vs 습격(pre5/pre1/start)으로 "습격일 때만 나오는 시그니처" 검증 가능.
- 샘플이 쌓이면 **패턴 분석** → “습격일 때만 공통으로 나오는 시그니처” 후보 정리.
- 그 결과로 **analyzer.py**를 처음부터 설계·구현.
- 실사용하면서 오탐/미탐 사례 수집 후 로직 보정.

### 5.3 현재 데이터
- 2건뿐이라 **뚜렷한 패턴이라고 단정할 수 없음**. “이 시간대에 이런 hex가 자주 보인다” 수준만 가능.

---

## 6. 폴더/파일 참고 (tools 구조)

| 경로 | 용도 | 빌드 |
|------|------|------|
| `engine/tools/analyzer/` | 패킷 분석·Discord 알림. 진입점 `analyzer/analyzer.py`. | `.github/workflows/build-analyzer.yml` → PacketAnalyzer.exe (utils, recording, mapping 포함). |
| `engine/tools/utils.py` | ConfigManager, Notifier(Discord). analyzer 빌드 시에만 포함. | analyzer와 함께 EXE에 번들. |
| `engine/tools/recording.py` | 패킷 녹화. 고정 10분 구간, `packet_YYYYMMDD_HHMM.json`. | analyzer와 함께 EXE에 번들. |
| `engine/tools/mapping.json` | **참고용만.** 신뢰하지 말 것. | analyzer 아티팩트에 복사. |
| `engine/tools/capture/` | 습격 OCR 감지. `raid_ocr.py` → EXE화. 옵션: exe와 같은 폴더의 `raid_ocr_config.json` 또는 기본값(EXE 시 60초 인터벌). | `.github/workflows/build-capture.yml` → RaidOcr.exe. Tesseract+한글은 사용자 PC 설치. |
| `engine/tools/label/` | 라벨링·패턴 분석. `raid_labeler.py`, `expand_raid_labels_batch.py`, `raid_pattern_analysis.py`. | Python 전용. EXE 빌드 없음. |
| `engine/tools/analyze/YYYYMMdd/` | 라벨링된 샘플 JSON + 해당 날짜 INDEX.md. | 데이터만. Git 제외 권장. |

- **analyzer**와 **capture**는 도구별로 분리된 EXE. 각 워크플로에서 해당 코드만 빌드.
- **label** 스크립트는 분석·라벨링용으로 Python 환경에서만 실행.

---

## 7. 빌드·실행 요약

| 도구 | 실행 방법 (Windows) | 비고 |
|------|---------------------|------|
| PacketAnalyzer | Actions에서 build-analyzer 실행 → 아티팩트 다운로드 후 PacketAnalyzer.exe + mapping.json 실행. | 관리자 권한. Discord Webhook은 시크릿으로 주입. |
| RaidOcr | Actions에서 build-capture 실행 → RaidOcr.exe. 같은 폴더에 `raid_ocr_config.json` (선택) 배치. | Tesseract + 한글 데이터 설치 필요. `raid_ocr_config.example.json` 참고. |

---

*마지막 정리: 2026-03-06*
