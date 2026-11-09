# Manchester United 팬 사이트 — API 조사 & 진행 계획

작성일: 2026-11-08 (현재 시즌 2026-27)

## 1. 데이터 출처(API) 조사 결과

| 용도 | API | 비용 | 필요 여부 | 비고 |
|---|---|---|---|---|
| 경기 일정·결과·리그 순위 | **football-data.org** v4 | 무료 (분당 10회) | **필수** | PL·챔스 포함, 맨유 team id 66. 무료는 스코어 지연 있음, 선수 스탯 없음 |
| 선수 시즌 통계·라인업·경기 이벤트·팀 스탯·이적 | **API-Football** (api-sports.io) v3 | 무료 100회/일, Pro $19/월 | **필수** | 무료 플랜은 조회 가능한 시즌 범위가 제한됨 → 키 발급 후 대시보드에서 2026 시즌 접근 가능 여부 먼저 확인. 안 되면 Pro 1개월 단위 결제 고려 |
| PL 선수 스탯 보조 (골·도움·출전시간·xG 등) | **Fantasy Premier League** 비공식 API (`/api/bootstrap-static/`, `/api/fixtures/`) | 무료, 키 없음 | 권장 | 비공식이라 구조 변경 가능. 현재 2026-27 시즌 제공 중. PL 경기만 |
| 과거 시즌 기록 (1886~) | Wikipedia "List of Manchester United F.C. seasons" + football-data.co.uk CSV | 무료 | 1회성 | 매년 바뀌지 않으므로 한 번 수집해서 DB에 저장 |
| 경기 분석 글 생성 | **Claude API** (Anthropic) | 종량제 (경기당 수 센트 수준) | 필수(분석 기능) | 경기 이벤트·스탯을 넣어 한국어 분석 생성 |
| 카카오톡 리마인드·결과 전송 | **카카오 메시지 API – 나에게 보내기** (`/v2/api/talk/memo/default/send`) | 무료 | 필수 | 개인 앱으로 사용 가능. 친구에게 보내기는 권한 심사 필요 → 본인에게만 전송 권장. 액세스 토큰 짧음, 리프레시 토큰 2개월(만료 1개월 전 갱신 시 새 값 반환 → 저장 로직 필요) |
| 스마트폰 알람 | **Google Calendar API** (권장) 또는 ICS 구독 피드 | 무료 | 필수 | 일정에 알림(1일 전/1시간 전) 넣으면 폰 기본 알림으로 울림. 카카오 톡캘린더 API는 별도 권한 신청 필요해서 2순위 |
| 시간 변환 | 라이브러리 (Python `zoneinfo`) | – | – | API 불필요. UTC 저장 → Europe/London(BST 반영)·Asia/Seoul 변환 |
| 로고·경기장 이미지 | 직접 준비 (위키미디어 커먼즈 경기장 사진 등) | – | – | 맨유 엠블럼은 상표권 대상 → **개인용 비공개 사이트**로 운영 권장 |

> 맨유 공식 홈페이지는 공개 API가 없음 → 디자인·톤 참고용으로만 사용.

### 추천 아키텍처 (전부 무료 범위)
```
GitHub 저장소 (private)
 ├─ data/manutd.db (SQLite)            ← 이번에 설계한 DB
 ├─ etl/*.py  (API 수집 → DB upsert)
 ├─ notify/*.py (카톡·캘린더·Claude 분석)
 ├─ site/  (정적 웹페이지, DB → JSON export 읽어서 표시)
 └─ .github/workflows/*.yml  (GitHub Actions cron 으로 자동 실행)
```
- 하루 1회: 일정·순위·선수 스탯·이적 동기화
- 15분마다: 경기 시작/종료 감지 → 리마인드·결과·분석 전송
- 나중에 실시간성이 더 필요하면 SQLite → Supabase(Postgres)로 이전 (스키마 그대로 호환)

## 2. 데이터베이스 (완료)
- `db/schema.sql` — 테이블 20개 + 뷰 3개
  - 클럽/역사: `club_info`, `history_timeline`, `managers`
  - 기록: `seasons`, `competitions`, `teams`, `season_standings`, `honours`
  - 선수: `players`, `squad_memberships`, `player_season_stats`, `transfers`
  - 경기: `matches`, `match_events`, `match_lineups`, `match_team_stats`, `player_match_stats`
  - 자동화: `match_analyses`, `notifications`, `sync_log`
- `db/seed.sql` — 클럽 정보, 대회 코드, 시즌(1992-93~2026-27), PL 시대 최종 순위(~2024-25), 우승 기록(리그 20·FA컵 13·리그컵 6·챔스 3 등), 주요 감독, 역사 타임라인
- `db/init_db.py` — `data/manutd.db` 생성

## 3. 이후 진행 리스트

### STEP 0. 환경 준비 (사용자 작업)
- [x] Python 3.13.17 설치 (winget, 2026-11-08) → `python db/init_db.py` 실행, `data/manutd.db` 생성 확인
- [x] football-data.org 가입 → 토큰 발급
- [x] API-Football 가입 → 키 발급, `scripts/check_apis.py` 점검 결과 **무료 플랜은 2022~2024 시즌만 허용, 2026 차단** → 현재 시즌은 football-data + FPL 로 구성. API-Football 무료는 2022-23~2024-25 과거 시즌 상세 백필용으로만 사용
- [~] ~~Anthropic 콘솔 API 키 발급~~ → 보류 (Claude API 미사용, 무료 템플릿 요약으로 진행)
- [x] Kakao Developers 앱 생성 → 카카오 로그인 활성화, `talk_message` 동의항목, Redirect URI·Client Secret(플랫폼 키 > REST API 키), 웹 도메인(제품 링크 관리) 등록
- [x] (2026-11-08 `scripts/test_calendar.py` 로 일정 생성 확인) Google Cloud 프로젝트 + Calendar API 활성화 → **서비스 계정** 생성 후 JSON 키 다운로드, 구글 캘린더에서 새 캘린더("Man Utd") 만들어 서비스 계정 이메일에 "일정 변경" 권한으로 공유 (OAuth 테스트 앱은 리프레시 토큰이 7일마다 만료돼 자동화에 부적합)
- [x] GitHub 저장소 `rolrend25-hub/manutd` (**public**, 2026-11-09) push 완료, Secrets `FOOTBALL_DATA_TOKEN` 등록, Pages(Actions 배포) 활성화 → https://rolrend25-hub.github.io/manutd/
- [x] `.env.example` → `.env` 로 복사 후 키 입력
- [x] `requirements.txt` (google-api-python-client, google-auth, tzdata) 설치

### STEP 1. 데이터 수집(ETL)
- [x] `etl/fetch_fixtures.py` — 일정·결과 (football-data) → `matches`, `teams` (2026-11-09 완료, 46경기 적재). 무료 플랜은 **PL·챔스만** 제공 → FA컵·EFL컵 경기는 별도 보완 필요. 공용 함수는 `etl/common.py`
- [x] `etl/fetch_standings.py` — PL·챔스 리그 페이즈 전체 순위표 → `league_table`(신규 테이블), 맨유 행 → `season_standings` (2026-11-09 완료)
- [x] `etl/fetch_players.py` — 스쿼드 34명·PL 시즌 합계·경기별 기록(출전시간·골·도움·카드·태클)·부상/징계 → `players`, `squad_memberships`, `player_season_stats`, `player_match_stats`, `player_availability`(신규), `matches.match_fpl_id` 연결 (2026-11-09 완료). 맨유 경기만 집계. 웹 '선수' 페이지 반영
- [x] `etl/fetch_match_details.py` (2026-11-09) — PL 종료 경기 양 팀 득점·도움·자책골·PK·카드·FPL 보너스 → `match_events` (분 정보 없음). `details_synced` 1=FPL 확정. 검증: 상세 골 수 = 스코어. 챔스 등 PL 외 대회는 무료 데이터에 상세 없음 → 스코어만
- [ ] `etl/fetch_transfers.py` — 무료 API 없음 → FPL 신규/제외 선수 감지 + 수동 입력(CSV)으로 `transfers`
- [ ] (선택) API-Football 무료로 2022-23~2024-25 시즌 라인업·이벤트 백필
- [ ] `etl/backfill_history.py` — 1886~1992 과거 시즌 순위 1회 수집
- [ ] 2025-26 시즌 전체 데이터 백필

### STEP 2. 웹페이지
- [x] (초안 2026-11-09) 디자인: 레드(#DA291C)·블랙·화이트 + 골드/블루 포인트, Anton + Noto Sans KR → `site/assets/style.css`
- [ ] 로고·올드 트래포드 이미지 기반 헤더 (초안은 'MU' 텍스트 마크 + CSS 그라데이션으로 대체 중)
- [~] 페이지 초안 `site/index.html` + `site/assets/app.js`: 홈(카운트다운·KST/영국시간·최근결과·다가오는 경기) / 일정·결과(대회 필터) / 순위(PL·UCL) / 역사(우승·연표·감독) / 시즌 기록 완료. 선수·이적·경기 분석은 데이터 수집 후
- [x] DB → JSON export `scripts/export_site_data.py` (→ `site/data/data.json`, `data.js`) + GitHub Pages 자동 배포
- [x] 경기 상세 페이지 `#match/<id>` (2026-11-09): 스코어 클릭 → 득점·도움·카드·최고 활약·경기 요약
- [x] 공식 엠블럼(football-data 이미지 링크, 저장소 미업로드)·헤드라인 한글/본문 영문 (2026-11-09)
- [x] 우측 상단 동기화 시점 배지 (KST, 36시간 넘게 갱신 없으면 노란색 '갱신 지연')

### STEP 3. 알림 자동화
- [ ] 카카오 토큰 최초 발급 스크립트 (브라우저 로그인 1회) + 리프레시 토큰 자동 갱신·저장
- [ ] 경기 일정 → Google 캘린더 일정 생성/수정 (알림 1일 전·1시간 전) → 폰 알람
- [ ] 카톡 리마인드: 경기 전날 + 킥오프 1시간 전 (영국/한국 시간 표기)
- [ ] 킥오프 시간 변경·연기 감지 시 캘린더 수정 + 카톡 안내

### STEP 4. 경기 결과 요약 + 카톡 전송 (무료 템플릿 방식)
- [x] (2026-11-09 `scripts/summarize_match.py`, 웹은 영문 `analysis_md` + 카톡용 한글 `summary_ko`) 경기 종료 감지 → 상세 데이터 수집 → **규칙 기반 템플릿 요약** 생성 (스코어·득점자/도움·카드·FPL 보너스 상위 선수·순위 변동·다음 경기) → `match_analyses` (`model` 컬럼에 `template-v1` 기록)
- [ ] 카톡 요약 + 웹 경기 페이지 링크 전송
- [ ] (나중에 선택) 요약 생성부를 교체 가능하게 분리해 두고, 원하면 Claude API 분석으로 전환

### STEP 5. 운영 자동화
- [x] GitHub Actions `.github/workflows/sync-and-deploy.yml` (2026-11-09 첫 실행 성공): 매일 05:00 UTC 전체 동기화 + 30분마다 점검·경기 종료 결과 대기 시 동기화 → 검증 통과 시에만 커밋·Pages 배포. 수동 실행 시 `test_alert` 옵션으로 알림 테스트 가능
- [x] 매 실행 검증 (2026-11-09): ① `scripts/check_privacy.py` 개인정보·비밀값·미허가 파일(허용 경로·`docs/approved_assets.txt` 미디어 승인) — 저장소 전체 + 커밋 직전 + 로컬 pre-commit 훅(`.githooks`) ② `scripts/check_sources.py` API 키·응답 구조 ③ `scripts/validate_data.py` 정합성·football-data↔FPL 교차검증·직전 커밋 DB 비교
- [x] 문제 시 알림 (2026-11-09 테스트: 이슈 #1 생성·소유자 할당 → 정상 실행 후 자동 닫힘 확인): `scripts/notify_status.py` → GitHub 이슈(소유자 할당 → 이메일·모바일 앱 푸시), 같은 문제 반복 알림 생략, 복구 시 자동 닫힘. 카톡 오류 알림은 STEP 3 카카오 토큰 후 추가
- [ ] 시즌 전환 자동 처리 (매년 7월 새 시즌 생성, `is_current` 전환)

## 결정 사항 (2026-11-08 확정)
1. 호스팅: **GitHub Pages + GitHub Actions** (무료, 정적). 무료 계정은 private 저장소 Pages 불가 → **public 저장소**로 결정 (2026-11-09). 비밀값은 Actions Secrets 에만, 커밋 전 자동 검사로 차단
2. 데이터 API: **무료 플랜만 사용**. API-Football 무료가 현재 시즌을 막으면 유료 결제 없이 **football-data + FPL** 로 구성 (PL 외 대회 선수 스탯·상세 이벤트는 제외 또는 football-data 범위 내에서만 표시). API-Football은 접근 가능한 범위에서 보조로만 사용
3. 폰 알람: **Google 캘린더 API** (알림 1일 전·1시간 전)
4. 경기 분석: **Claude API 미사용** (Pro 구독과 API는 별도 과금) → 무료 템플릿 요약. 추후 전환 가능하도록 구조만 분리
