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
- [x] `etl/fetch_fixtures.py` — 일정·결과 (football-data) → `matches`, `teams` (2026-11-09 완료, 46경기 적재). 무료 플랜은 **PL·챔스만** 제공 → FA컵·EFL컵·커뮤니티실드는 `etl/fetch_cups.py`(위키백과 시즌 문서 컵 표, 2026-11-09)로 보완: 날짜·상대·스코어·승부차기·맨유 득점자(분). 킥오프 시각 없음 → `kickoff_confirmed=0`(캘린더 종일 일정, 리마인드 없음). 식별 `matches.match_ext_id`. 공용 함수는 `etl/common.py`
- [x] `etl/fetch_standings.py` — PL·챔스 리그 페이즈 전체 순위표 → `league_table`(신규 테이블), 맨유 행 → `season_standings` (2026-11-09 완료)
- [x] `etl/fetch_players.py` — 스쿼드 34명·PL 시즌 합계·경기별 기록(출전시간·골·도움·카드·태클)·부상/징계 → `players`, `squad_memberships`, `player_season_stats`, `player_match_stats`, `player_availability`(신규), `matches.match_fpl_id` 연결 (2026-11-09 완료). 맨유 경기만 집계. 웹 '선수' 페이지 반영
- [x] `etl/fetch_match_details.py` (2026-11-09) — PL 종료 경기 양 팀 득점·도움·자책골·PK·카드·FPL 보너스 → `match_events` (분 정보 없음). `details_synced` 1=FPL 확정. 검증: 상세 골 수 = 스코어. 챔스 등 PL 외 대회는 무료 데이터에 상세 없음 → 스코어만
- [x] (2026-11-09) `etl/fetch_transfers.py` — 위키백과 시즌 문서 Transfers 표(In/Out/Loan) → `transfers` (2026-27 41건, 2025-26 47건). 매 동기화 실행, 위키에서 사라진 행 삭제, 실패해도 전체 동기화는 계속(경고). 웹 '이적' 페이지(시즌별 영입·방출·임대)
- [x] (2026-11-12) 컵 대회 킥오프 시각 — `etl/fetch_cups.py` 가 대회 문서('<시즌> FA Cup' / '<시즌> EFL Cup' / '<연도> FA Community Shield') 경기 박스의 날짜·시각(BST/GMT)을 찾아 `kickoff_confirmed=1` → 컵 경기도 캘린더 시간 일정·카톡 리마인드. 시각 확정·변경은 KICKOFF_CHANGE 카톡 안내. 2025-26·2026-27 컵 3경기 시각 확인(예: 16 Sep 2026 20:00 BST)
- [x] (2026-11-12) PL 출전 선수 — `etl/fetch_players.py` 가 FPL 경기별 'starts' → `match_lineups`(맨유 선발/교체, 등번호·포지션). 웹 경기 상세 '출전 선수'(선발 XI·교체 출전, 출전시간·골·도움·카드). 벤치 미출전·포메이션·상대 팀 라인업은 무료 출처 없음. 검증: 선발 11명 초과 오류, 미만 경고(시즌 중 이적 선수 누락 가능). 이번 시즌 10경기 모두 선발 11명
- [x] (2026-11-12) `etl/sync_honours.py` — 우승 기록 자동 계산: 시즌 기록(리그 1위·FA컵/리그컵/유럽대회·슈퍼컵·인터컨티넨털컵·클럽월드컵 Winners) + 진행 중 시즌 결승 승리(승부차기 포함, 커뮤니티실드 포함) → 없으면 `honours` 추가(note 'auto: …'), 기존 기록인데 근거 없으면 ⚠ (커뮤니티실드 과거분은 근거 데이터 없어 비교 제외). 기존 47건 전부 일치 확인
- [x] (2026-11-12) `etl/fetch_club.py` — 매 동기화 실행. ① 감독: football-data `/teams/66` 공식 현직 감독 + 위키백과 'List of Manchester United F.C. managers' 전체 33명(재임 기간·전적·임시 감독) → `managers`. 위키 현직 = 공식일 때만 교체, 다르면 기존 유지 + ⚠ 알림, 감독 교체 시 ⚠ 알림 1회 (Amorim → Carrick 2026-01-13 반영) ② 이적 교차검증: 위키 이적 ↔ 공식 1군 명단(football-data)·FPL 상태(입단일·이탈·임대) → `transfers.verify_status` (verified 공식 확인 / consistent 모순 없음 / unverified 확인 불가(유스 등) / conflict 불일치), 위키 누락 의심(FPL 입단·이탈인데 위키 기록 없음) → `transfer_checks`. 새 불일치·누락만 ⚠ 알림(GitHub 이슈), 해소 시 자동 해소 처리. 현재 시즌만 검증. 웹 '이적' Check 열·'확인 필요' 목록, '역사' 역대 감독 전체·전적
- [ ] (선택) API-Football 무료로 2022-23~2024-25 시즌 라인업·이벤트 백필
- [x] (2026-11-09) `etl/backfill_history.py` — 위키백과 'List of Manchester United F.C. seasons' → 1888-89~2025-26 128시즌 리그 성적·FA컵·리그컵·유럽대회·최다 득점자 (`season_standings`). 검증: W+D+L=경기 수, 승점(1990-91 1점 감점 예외), 1992년 이후 기존 순위 일치. 웹 '시즌 기록' 시대별 필터
- [x] (2026-11-09) 2025-26 시즌 백필: PL 38경기·순위표(football-data, 위키와 일치 확인) + FA컵·EFL컵(위키). 선수별 경기 기록은 무료 출처 없음(FPL 은 현재 시즌만)

### STEP 2. 웹페이지
- [x] (초안 2026-11-09) 디자인: 레드(#DA291C)·블랙·화이트 + 골드/블루 포인트, Anton + Noto Sans KR → `site/assets/style.css`
- [ ] 로고·올드 트래포드 이미지 기반 헤더 (초안은 'MU' 텍스트 마크 + CSS 그라데이션으로 대체 중)
- [~] 페이지 초안 `site/index.html` + `site/assets/app.js`: 홈(카운트다운·KST/영국시간·최근결과·다가오는 경기) / 일정·결과(대회 필터) / 순위(PL·UCL) / 역사(우승·연표·감독) / 시즌 기록 완료. 선수·이적·경기 분석은 데이터 수집 후
- [x] DB → JSON export `scripts/export_site_data.py` (→ `site/data/data.json`, `data.js`) + GitHub Pages 자동 배포
- [x] 경기 상세 페이지 `#match/<id>` (2026-11-09): 스코어 클릭 → 득점·도움·카드·최고 활약·경기 요약
- [x] 공식 엠블럼(football-data 이미지 링크, 저장소 미업로드)·헤드라인 한글/본문 영문 (2026-11-09)
- [x] 우측 상단 동기화 시점 배지 (KST, 36시간 넘게 갱신 없으면 노란색 '갱신 지연')

### STEP 3. 알림 자동화
- [x] (2026-11-09 로그인·시험 메시지·Secrets 등록 완료) 카카오 토큰 최초 발급 `scripts/kakao_login.py` (브라우저 로그인 1회 → `.env` 저장 + 시험 메시지) + 리프레시 토큰 자동 갱신: `notify/kakao.py` 가 새 토큰을 받으면 로컬은 `.env`, Actions 는 Secrets(`GH_SECRETS_TOKEN` 개인 토큰, 이 저장소 Secrets 쓰기 권한만)에 자동 저장
- [x] (2026-11-09) `notify/sync_calendar.py` — 이번 시즌 전 경기 → Google 캘린더 (46경기 등록 확인). 바뀐 일정만 수정(시간 변경·연기·스코어), 취소 경기 삭제, 시간 미정은 종일 일정. 알림은 캘린더 기본 알림(1일 전·1시간 전). Actions 는 커밋 후 단계에서 실행 (Secrets `GOOGLE_SERVICE_ACCOUNT_KEY`·`GOOGLE_CALENDAR_ID` 등록, Actions 첫 실행 성공)
- [x] (2026-11-09 Actions 연결, 첫 실제 발송은 리버풀전 하루 전 2026-11-21 예정) `notify/send_kakao.py` — 카톡 리마인드: 킥오프 24시간 전 + 1시간 전 (한국/영국 시간). 30분마다 실행, 보낸 기록은 `notifications` 에 커밋 → 중복 없음.
- [x] (2026-11-09) 킥오프 시간 변경·확정·연기 감지: `etl/fetch_fixtures.py` → `notifications`(KICKOFF_CHANGE) 대기열 → 카톡 안내 + 리마인드 재설정. 캘린더는 다음 동기화에서 자동 수정

### STEP 4. 경기 결과 요약 + 카톡 전송 (무료 템플릿 방식)
- [x] (2026-11-09 `scripts/summarize_match.py`, 웹은 영문 `analysis_md` + 카톡용 한글 `summary_ko`) 경기 종료 감지 → 상세 데이터 수집 → **규칙 기반 템플릿 요약** 생성 (스코어·득점자/도움·카드·FPL 보너스 상위 선수·순위 변동·다음 경기) → `match_analyses` (`model` 컬럼에 `template-v1` 기록)
- [x] (2026-11-09) 카톡 결과 요약 + 웹 경기 페이지 링크 전송: `notify/send_kakao.py` RESULT — 결과·득점·카드·최고 활약·PL 순위·다음 경기. PL 은 FPL 상세 확정 후(늦으면 킥오프 6시간 뒤), 최근 2일 경기만. 200자 넘으면 카드 목록부터 생략
- [ ] (나중에 선택) 요약 생성부를 교체 가능하게 분리해 두고, 원하면 Claude API 분석으로 전환

### STEP 5. 운영 자동화
- [x] GitHub Actions `.github/workflows/sync-and-deploy.yml` (2026-11-09 첫 실행 성공): 매일 05:00 UTC 전체 동기화 + 30분마다 점검·경기 종료 결과 대기 시 동기화 → 검증 통과 시에만 커밋·Pages 배포. 수동 실행 시 `test_alert` 옵션으로 알림 테스트 가능
- [x] 매 실행 검증 (2026-11-09): ① `scripts/check_privacy.py` 개인정보·비밀값·미허가 파일(허용 경로·`docs/approved_assets.txt` 미디어 승인) — 저장소 전체 + 커밋 직전 + 로컬 pre-commit 훅(`.githooks`) ② `scripts/check_sources.py` API 키·응답 구조 ③ `scripts/validate_data.py` 정합성·football-data↔FPL 교차검증·직전 커밋 DB 비교
- [x] 문제 시 알림 (2026-11-09 테스트: 이슈 #1 생성·소유자 할당 → 정상 실행 후 자동 닫힘 확인): `scripts/notify_status.py` → GitHub 이슈(소유자 할당 → 이메일·모바일 앱 푸시), 같은 문제 반복 알림 생략, 복구 시 자동 닫힘. 카톡 오류 알림은 STEP 3 카카오 토큰 후 추가
- [x] (2026-11-12) 시즌 전환 자동 처리 `etl/season_rollover.py` — 매 동기화 맨 앞. football-data PL currentSeason 시작 연도 = 현재 시즌+1 이고 6월 1일 이후면 새 시즌 추가·`is_current` 전환 → 지난 시즌 최종 순위(is_final)·결과·컵·이적 재수집 + `backfill_history.py` → ⚠ 알림 1회. FPL 이 아직 지난 시즌이면 `fetch_players.py` 는 대기(덮어쓰기 방지). 검증은 새 시즌 개막 전(종료 경기 0) 일정·순위표 비어 있음을 경고로 처리. 시뮬레이션(복사본 DB, `MANUTD_DB`·`--force-year`)으로 확인
- [x] (2026-11-12) 역대 시즌 기록 매일 갱신 — `backfill_history.py` 를 매 동기화에 포함 (위키 수정·지난 시즌 결과 반영, 현재 시즌은 건드리지 않음)

## 결정 사항 (2026-11-08 확정)
1. 호스팅: **GitHub Pages + GitHub Actions** (무료, 정적). 무료 계정은 private 저장소 Pages 불가 → **public 저장소**로 결정 (2026-11-09). 비밀값은 Actions Secrets 에만, 커밋 전 자동 검사로 차단
2. 데이터 API: **무료 플랜만 사용**. API-Football 무료가 현재 시즌을 막으면 유료 결제 없이 **football-data + FPL** 로 구성 (PL 외 대회 선수 스탯·상세 이벤트는 제외 또는 football-data 범위 내에서만 표시). API-Football은 접근 가능한 범위에서 보조로만 사용
3. 폰 알람: **Google 캘린더 API** (알림 1일 전·1시간 전)
4. 경기 분석: **Claude API 미사용** (Pro 구독과 API는 별도 과금) → 무료 템플릿 요약. 추후 전환 가능하도록 구조만 분리
