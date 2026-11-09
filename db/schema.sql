-- =====================================================================
--  Manchester United Fan Site - Database Schema (SQLite, Postgres 호환 위주)
--  원칙
--   * 모든 경기 시각은 UTC(ISO-8601)로 저장 → 화면/알림에서 Europe/London, Asia/Seoul 로 변환
--     (영국은 서머타임(BST)이 있어 고정 시차(+8/+9h)로 계산하면 틀림)
--   * 외부 API 마다 ID 체계가 달라서 핵심 엔터티에 *_fd_id(football-data.org),
--     *_af_id(API-Football), *_fpl_id(FPL) 매핑 컬럼을 둔다
--   * 자동 수집 결과는 sync_log 에 남겨 실패 추적
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. 클럽 기본 정보 / 역사
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS club_info (
    id              INTEGER PRIMARY KEY CHECK (id = 1),   -- 단일 행
    name            TEXT NOT NULL,
    name_ko         TEXT,
    nickname        TEXT,
    founded_year    INTEGER,
    founded_as      TEXT,
    stadium         TEXT,
    stadium_capacity INTEGER,
    city            TEXT,
    crest_path      TEXT,          -- 로컬 에셋 경로 (assets/img/...)
    stadium_img_path TEXT,
    team_fd_id      INTEGER,       -- football-data.org team id (66)
    team_af_id      INTEGER,       -- API-Football team id (33)
    team_fpl_code   INTEGER        -- FPL team code
);

CREATE TABLE IF NOT EXISTS history_timeline (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL,
    date        TEXT,              -- YYYY-MM-DD (알면)
    title       TEXT NOT NULL,
    title_ko    TEXT,
    body_ko     TEXT,
    category    TEXT,              -- founding / tragedy / trophy / manager / stadium / etc
    image_path  TEXT,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS managers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    name_ko     TEXT,
    nationality TEXT,
    start_date  TEXT,
    end_date    TEXT,              -- NULL = 현직
    is_caretaker INTEGER DEFAULT 0,
    note        TEXT,
    note_en     TEXT               -- 웹페이지 영문 본문용
);

-- ---------------------------------------------------------------------
-- 2. 시즌 / 대회 / 상대팀
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seasons (
    season      TEXT PRIMARY KEY,  -- '2026-27'
    start_year  INTEGER NOT NULL,
    start_date  TEXT,
    end_date    TEXT,
    is_current  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS competitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,   -- PL, FAC, ELC, UCL, UEL, UECL, CS, FL1(구 1부리그) ...
    name        TEXT NOT NULL,
    name_ko     TEXT,
    type        TEXT,                   -- league / cup / europe / super_cup / friendly
    comp_fd_id  INTEGER,
    comp_af_id  INTEGER
);

CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    short_name  TEXT,
    name_ko     TEXT,
    tla         TEXT,                   -- 3글자 약어 (ARS, LIV ...)
    crest_url   TEXT,
    team_fd_id  INTEGER UNIQUE,
    team_af_id  INTEGER UNIQUE,
    team_fpl_id INTEGER
);

-- ---------------------------------------------------------------------
-- 3. 연도별 순위 / 우승 기록
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS season_standings (
    season          TEXT NOT NULL REFERENCES seasons(season),
    competition_code TEXT NOT NULL,     -- 'PL' 또는 'FL1' 등 리그
    division        TEXT,               -- 'Premier League', 'First Division', 'Second Division'
    position        INTEGER,
    played          INTEGER,
    won             INTEGER,
    drawn           INTEGER,
    lost            INTEGER,
    goals_for       INTEGER,
    goals_against   INTEGER,
    points          INTEGER,
    top_scorer      TEXT,
    top_scorer_goals INTEGER,
    fa_cup_result   TEXT,               -- 'Winners', 'R16' ...
    league_cup_result TEXT,
    europe_competition TEXT,
    europe_result   TEXT,
    is_final        INTEGER DEFAULT 1,  -- 진행 중 시즌은 0 (자동 갱신)
    source          TEXT,
    updated_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (season, competition_code)
);

-- 현재 시즌 리그 전체 순위표 (웹 '순위' 페이지용, 매일 덮어씀)
CREATE TABLE IF NOT EXISTS league_table (
    season          TEXT NOT NULL REFERENCES seasons(season),
    competition_code TEXT NOT NULL,     -- 'PL' / 'UCL'(리그 페이즈)
    position        INTEGER NOT NULL,
    team_id         INTEGER REFERENCES teams(id),
    team_name       TEXT NOT NULL,
    played          INTEGER,
    won             INTEGER,
    drawn           INTEGER,
    lost            INTEGER,
    goals_for       INTEGER,
    goals_against   INTEGER,
    goal_diff       INTEGER,
    points          INTEGER,
    form            TEXT,               -- 'W,D,L,W,W' (제공될 때만)
    updated_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (season, competition_code, position)
);

CREATE TABLE IF NOT EXISTS honours (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_code TEXT NOT NULL,
    competition_name TEXT NOT NULL,
    season          TEXT NOT NULL,      -- '1998-99' 또는 단일 연도 컵은 '1999'
    final_opponent  TEXT,
    final_score     TEXT,
    note            TEXT,
    UNIQUE (competition_code, season)
);

-- ---------------------------------------------------------------------
-- 4. 선수 / 스쿼드 / 시즌 통계
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    known_as        TEXT,
    name_ko         TEXT,
    position        TEXT,               -- GK / DF / MF / FW
    detailed_position TEXT,
    nationality     TEXT,
    date_of_birth   TEXT,
    height_cm       INTEGER,
    preferred_foot  TEXT,
    photo_url       TEXT,
    is_legend       INTEGER DEFAULT 0,  -- 역사 페이지용 레전드
    player_fd_id    INTEGER UNIQUE,
    player_af_id    INTEGER UNIQUE,
    player_fpl_code INTEGER UNIQUE,     -- FPL 'code' 는 시즌이 바뀌어도 유지됨 (id 는 매 시즌 바뀜)
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS squad_memberships (
    player_id       INTEGER NOT NULL REFERENCES players(id),
    season          TEXT NOT NULL REFERENCES seasons(season),
    shirt_number    INTEGER,
    joined_date     TEXT,
    left_date       TEXT,
    on_loan_from    TEXT,
    status          TEXT DEFAULT 'active',  -- active / loaned_out / left / academy
    PRIMARY KEY (player_id, season)
);

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id       INTEGER NOT NULL REFERENCES players(id),
    season          TEXT NOT NULL REFERENCES seasons(season),
    competition_code TEXT NOT NULL,     -- 'ALL' = 전 대회 합계
    appearances     INTEGER DEFAULT 0,
    starts          INTEGER DEFAULT 0,
    minutes         INTEGER DEFAULT 0,
    goals           INTEGER DEFAULT 0,
    assists         INTEGER DEFAULT 0,
    yellow_cards    INTEGER DEFAULT 0,
    red_cards       INTEGER DEFAULT 0,
    clean_sheets    INTEGER DEFAULT 0,
    saves           INTEGER,
    xg              REAL,
    xa              REAL,
    avg_rating      REAL,
    source          TEXT,
    updated_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (player_id, season, competition_code)
);

-- 현재 출전 가능 여부 (부상·징계·임대 등, FPL 'status'/'news' 기준, 매일 덮어씀)
CREATE TABLE IF NOT EXISTS player_availability (
    player_id       INTEGER PRIMARY KEY REFERENCES players(id),
    status          TEXT,               -- a 가능 / d 불확실 / i 부상 / s 징계 / u 이탈(임대·이적) / n 자격 없음
    chance_next     INTEGER,            -- 다음 라운드 출전 가능성 % (NULL = 정보 없음)
    news            TEXT,
    news_added_utc  TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- 5. 이적 (영입/방출/임대)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transfers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER REFERENCES players(id),
    player_name     TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('in','out')),
    transfer_type   TEXT,               -- permanent / loan / loan_return / free / youth_promotion / release
    from_club       TEXT,
    to_club         TEXT,
    fee_eur         INTEGER,            -- 정렬/합계용 숫자
    fee_text        TEXT,               -- '£50m + add-ons' 등 원문
    transfer_date   TEXT,
    transfer_window TEXT,             -- '2026-summer' / '2027-winter'
    season          TEXT REFERENCES seasons(season),
    status          TEXT DEFAULT 'confirmed',  -- confirmed / official_pending / rumour
    source          TEXT,
    source_url      TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (player_name, direction, transfer_date)
);

-- ---------------------------------------------------------------------
-- 6. 경기 (일정 + 결과 + 세부)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    season          TEXT NOT NULL REFERENCES seasons(season),
    competition_code TEXT NOT NULL,
    stage           TEXT,               -- REGULAR_SEASON / ROUND_OF_16 / FINAL ...
    matchday        INTEGER,
    kickoff_utc     TEXT NOT NULL,      -- '2026-11-08T16:30:00Z'
    kickoff_confirmed INTEGER DEFAULT 1,-- TV 중계 일정 미확정이면 0 (PL 은 수주 전까지 바뀜)
    home_away       TEXT NOT NULL CHECK (home_away IN ('H','A','N')),
    opponent_id     INTEGER REFERENCES teams(id),
    opponent_name   TEXT NOT NULL,
    venue           TEXT,
    status          TEXT NOT NULL DEFAULT 'SCHEDULED',
                    -- SCHEDULED / TIMED / IN_PLAY / PAUSED / FINISHED / POSTPONED / CANCELLED
    mu_score        INTEGER,
    opp_score       INTEGER,
    mu_score_ht     INTEGER,
    opp_score_ht    INTEGER,
    mu_pens         INTEGER,
    opp_pens        INTEGER,
    result          TEXT CHECK (result IN ('W','D','L') OR result IS NULL),
    referee         TEXT,
    attendance      INTEGER,
    match_fd_id     INTEGER UNIQUE,
    match_af_id     INTEGER UNIQUE,
    match_fpl_id    INTEGER,
    match_ext_id    TEXT UNIQUE,        -- football-data 에 없는 경기 (예: 'wiki:2026-27:ELC:Third round')
    details_synced  INTEGER DEFAULT 0,  -- 이벤트/라인업/스탯 수집 완료 여부
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_matches_kickoff ON matches(kickoff_utc);
CREATE INDEX IF NOT EXISTS ix_matches_season ON matches(season, competition_code);

CREATE TABLE IF NOT EXISTS match_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    minute          INTEGER,
    extra_minute    INTEGER,
    team_side       TEXT CHECK (team_side IN ('MU','OPP')),
    event_type      TEXT,               -- goal / own_goal / penalty / missed_penalty / yellow / red / sub / var
    player_name     TEXT,
    player_id       INTEGER REFERENCES players(id),
    assist_name     TEXT,
    detail          TEXT
);

CREATE TABLE IF NOT EXISTS match_lineups (
    match_id        INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_side       TEXT NOT NULL CHECK (team_side IN ('MU','OPP')),
    player_name     TEXT NOT NULL,
    player_id       INTEGER REFERENCES players(id),
    shirt_number    INTEGER,
    position        TEXT,
    is_starter      INTEGER DEFAULT 1,
    formation       TEXT,
    PRIMARY KEY (match_id, team_side, player_name)
);

CREATE TABLE IF NOT EXISTS match_team_stats (
    match_id        INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_side       TEXT NOT NULL CHECK (team_side IN ('MU','OPP')),
    possession_pct  REAL,
    shots           INTEGER,
    shots_on_target INTEGER,
    xg              REAL,
    corners         INTEGER,
    fouls           INTEGER,
    offsides        INTEGER,
    passes          INTEGER,
    pass_accuracy_pct REAL,
    saves           INTEGER,
    PRIMARY KEY (match_id, team_side)
);

CREATE TABLE IF NOT EXISTS player_match_stats (
    match_id        INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    minutes         INTEGER,
    goals           INTEGER DEFAULT 0,
    assists         INTEGER DEFAULT 0,
    shots           INTEGER,
    key_passes      INTEGER,
    tackles         INTEGER,
    rating          REAL,
    yellow          INTEGER DEFAULT 0,
    red             INTEGER DEFAULT 0,
    PRIMARY KEY (match_id, player_id)
);

-- ---------------------------------------------------------------------
-- 7. 경기 분석 / 알림 / 동기화 로그 (자동화용)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match_analyses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL UNIQUE REFERENCES matches(id) ON DELETE CASCADE,
    model           TEXT,               -- 'claude-sonnet-5-5' 등
    summary_ko      TEXT,               -- 카톡용 짧은 요약 (템플릿 텍스트 200자 제한 고려)
    analysis_md     TEXT,               -- 웹페이지용 전체 분석
    player_of_match TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,      -- REMIND_D1 / REMIND_H1 / LINEUP / RESULT / CALENDAR_EVENT
    channel         TEXT NOT NULL,      -- kakao_memo / google_calendar / ics / push
    scheduled_utc   TEXT NOT NULL,
    sent_utc        TEXT,
    status          TEXT DEFAULT 'pending',  -- pending / sent / failed / skipped
    external_ref    TEXT,               -- 캘린더 event id 등 (일정 변경 시 수정용)
    error           TEXT,
    UNIQUE (match_id, kind, channel)
);
CREATE INDEX IF NOT EXISTS ix_notif_due ON notifications(status, scheduled_utc);

CREATE TABLE IF NOT EXISTS sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,      -- football-data / api-football / fpl / kakao / claude
    job             TEXT NOT NULL,      -- fixtures / results / standings / players / transfers ...
    started_utc     TEXT DEFAULT (datetime('now')),
    finished_utc    TEXT,
    status          TEXT,               -- ok / partial / error
    rows_upserted   INTEGER,
    api_calls       INTEGER,
    message         TEXT
);

-- ---------------------------------------------------------------------
-- 8. 화면용 뷰
-- ---------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_upcoming_matches AS
SELECT m.*,
       c.name_ko AS competition_ko
FROM matches m
LEFT JOIN competitions c ON c.code = m.competition_code
WHERE m.status IN ('SCHEDULED','TIMED','POSTPONED')
  AND m.kickoff_utc >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-3 hours')
ORDER BY m.kickoff_utc;

CREATE VIEW IF NOT EXISTS v_recent_results AS
SELECT m.*,
       c.name_ko AS competition_ko,
       a.summary_ko
FROM matches m
LEFT JOIN competitions c ON c.code = m.competition_code
LEFT JOIN match_analyses a ON a.match_id = m.id
WHERE m.status = 'FINISHED'
ORDER BY m.kickoff_utc DESC;

CREATE VIEW IF NOT EXISTS v_honours_count AS
SELECT competition_code, competition_name, COUNT(*) AS titles
FROM honours GROUP BY competition_code, competition_name
ORDER BY titles DESC;
