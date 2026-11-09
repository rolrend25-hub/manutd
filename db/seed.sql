-- =====================================================================
--  초기(정적) 데이터 - 거의 변하지 않는 사실 위주로 수기 입력
--  * 순위 상세(승/무/패/득실/승점), 1992 이전 시즌, 선수 정보는
--    ETL 스크립트(다음 단계)로 채운다.
--  * source = 'manual-seed' 행은 웹 공개 전 한 번 더 검수할 것.
-- =====================================================================

INSERT OR REPLACE INTO club_info
 (id, name, name_ko, nickname, founded_year, founded_as, stadium, stadium_capacity, city,
  crest_path, stadium_img_path, team_fd_id, team_af_id, team_fpl_code)
VALUES
 (1, 'Manchester United', '맨체스터 유나이티드', 'The Red Devils', 1878, 'Newton Heath LYR F.C.',
  'Old Trafford', 74000, 'Manchester',
  'assets/img/crest.svg', 'assets/img/old-trafford.jpg', 66, 33, 1);
-- stadium_capacity 는 근사치. team_fd_id / team_af_id 는 첫 API 호출 때 실제 값으로 검증.

-- 대회 코드 -------------------------------------------------------------
INSERT OR IGNORE INTO competitions (code, name, name_ko, type, comp_fd_id, comp_af_id) VALUES
 ('PL',   'Premier League',               '프리미어리그',          'league',    2021, 39),
 ('FL1',  'Football League First Division','풋볼리그 1부 (1992 이전)','league',  NULL, NULL),
 ('FL2',  'Football League Second Division','풋볼리그 2부 (1992 이전)','league', NULL, NULL),
 ('FAC',  'FA Cup',                       'FA컵',                 'cup',       NULL, 45),
 ('ELC',  'EFL Cup',                      'EFL컵 (카라바오컵)',     'cup',       NULL, 48),
 ('UCL',  'UEFA Champions League',        'UEFA 챔피언스리그',      'europe',    2001, 2),
 ('UEL',  'UEFA Europa League',           'UEFA 유로파리그',        'europe',    NULL, 3),
 ('UECL', 'UEFA Conference League',       'UEFA 컨퍼런스리그',      'europe',    NULL, 848),
 ('UCWC', 'European Cup Winners'' Cup',   'UEFA 컵위너스컵',        'europe',    NULL, NULL),
 ('USC',  'UEFA Super Cup',               'UEFA 슈퍼컵',           'super_cup', NULL, 531),
 ('ICC',  'Intercontinental Cup',         '인터콘티넨털컵',         'super_cup', NULL, NULL),
 ('CWC',  'FIFA Club World Cup',          'FIFA 클럽월드컵',        'super_cup', NULL, 15),
 ('CS',   'FA Community Shield',          'FA 커뮤니티실드',        'super_cup', NULL, 528),
 ('FRI',  'Friendly',                     '친선경기',              'friendly',  NULL, 667);

-- 시즌 (프리미어리그 출범 1992-93 ~ 현재) ----------------------------------
WITH RECURSIVE y(n) AS (SELECT 1992 UNION ALL SELECT n + 1 FROM y WHERE n < 2026)
INSERT OR IGNORE INTO seasons (season, start_year, is_current)
SELECT printf('%d-%02d', n, (n + 1) % 100), n, CASE WHEN n = 2026 THEN 1 ELSE 0 END FROM y;

-- PL 시대 최종 순위 (상세 수치는 ETL 로 보강) ------------------------------
INSERT OR IGNORE INTO season_standings (season, competition_code, division, position, is_final, source) VALUES
 ('1992-93','PL','Premier League',1,1,'manual-seed'),
 ('1993-94','PL','Premier League',1,1,'manual-seed'),
 ('1994-95','PL','Premier League',2,1,'manual-seed'),
 ('1995-96','PL','Premier League',1,1,'manual-seed'),
 ('1996-97','PL','Premier League',1,1,'manual-seed'),
 ('1997-98','PL','Premier League',2,1,'manual-seed'),
 ('1998-99','PL','Premier League',1,1,'manual-seed'),
 ('1999-00','PL','Premier League',1,1,'manual-seed'),
 ('2000-01','PL','Premier League',1,1,'manual-seed'),
 ('2001-02','PL','Premier League',3,1,'manual-seed'),
 ('2002-03','PL','Premier League',1,1,'manual-seed'),
 ('2003-04','PL','Premier League',3,1,'manual-seed'),
 ('2004-05','PL','Premier League',3,1,'manual-seed'),
 ('2005-06','PL','Premier League',2,1,'manual-seed'),
 ('2006-07','PL','Premier League',1,1,'manual-seed'),
 ('2007-08','PL','Premier League',1,1,'manual-seed'),
 ('2008-09','PL','Premier League',1,1,'manual-seed'),
 ('2009-10','PL','Premier League',2,1,'manual-seed'),
 ('2010-11','PL','Premier League',1,1,'manual-seed'),
 ('2011-12','PL','Premier League',2,1,'manual-seed'),
 ('2012-13','PL','Premier League',1,1,'manual-seed'),
 ('2013-14','PL','Premier League',7,1,'manual-seed'),
 ('2014-15','PL','Premier League',4,1,'manual-seed'),
 ('2015-16','PL','Premier League',5,1,'manual-seed'),
 ('2016-17','PL','Premier League',6,1,'manual-seed'),
 ('2017-18','PL','Premier League',2,1,'manual-seed'),
 ('2018-19','PL','Premier League',6,1,'manual-seed'),
 ('2019-20','PL','Premier League',3,1,'manual-seed'),
 ('2020-21','PL','Premier League',2,1,'manual-seed'),
 ('2021-22','PL','Premier League',6,1,'manual-seed'),
 ('2022-23','PL','Premier League',3,1,'manual-seed'),
 ('2023-24','PL','Premier League',8,1,'manual-seed'),
 ('2024-25','PL','Premier League',15,1,'manual-seed');
-- 2025-26 최종 순위, 2026-27 진행 순위는 standings API 로 자동 입력

-- 우승 기록 --------------------------------------------------------------
-- 리그 우승 20회
INSERT OR IGNORE INTO honours (competition_code, competition_name, season) VALUES
 ('FL1','League Champions','1907-08'),('FL1','League Champions','1910-11'),
 ('FL1','League Champions','1951-52'),('FL1','League Champions','1955-56'),
 ('FL1','League Champions','1956-57'),('FL1','League Champions','1964-65'),
 ('FL1','League Champions','1966-67'),
 ('PL','League Champions','1992-93'),('PL','League Champions','1993-94'),
 ('PL','League Champions','1995-96'),('PL','League Champions','1996-97'),
 ('PL','League Champions','1998-99'),('PL','League Champions','1999-00'),
 ('PL','League Champions','2000-01'),('PL','League Champions','2002-03'),
 ('PL','League Champions','2006-07'),('PL','League Champions','2007-08'),
 ('PL','League Champions','2008-09'),('PL','League Champions','2010-11'),
 ('PL','League Champions','2012-13');

-- FA컵 13회
INSERT OR IGNORE INTO honours (competition_code, competition_name, season) VALUES
 ('FAC','FA Cup','1909'),('FAC','FA Cup','1948'),('FAC','FA Cup','1963'),
 ('FAC','FA Cup','1977'),('FAC','FA Cup','1983'),('FAC','FA Cup','1985'),
 ('FAC','FA Cup','1990'),('FAC','FA Cup','1994'),('FAC','FA Cup','1996'),
 ('FAC','FA Cup','1999'),('FAC','FA Cup','2004'),('FAC','FA Cup','2016'),
 ('FAC','FA Cup','2024');

-- 리그컵 6회
INSERT OR IGNORE INTO honours (competition_code, competition_name, season) VALUES
 ('ELC','League Cup','1992'),('ELC','League Cup','2006'),('ELC','League Cup','2009'),
 ('ELC','League Cup','2010'),('ELC','League Cup','2017'),('ELC','League Cup','2023');

-- 유럽 / 세계 대회
INSERT OR IGNORE INTO honours (competition_code, competition_name, season, final_opponent, final_score) VALUES
 ('UCL','European Cup / Champions League','1968','Benfica','4-1 (a.e.t.)'),
 ('UCL','European Cup / Champions League','1999','Bayern Munich','2-1'),
 ('UCL','European Cup / Champions League','2008','Chelsea','1-1 (6-5 pens)'),
 ('UEL','UEFA Europa League','2017','Ajax','2-0'),
 ('UCWC','European Cup Winners'' Cup','1991','Barcelona','2-1'),
 ('USC','UEFA Super Cup','1991','Red Star Belgrade','1-0'),
 ('ICC','Intercontinental Cup','1999','Palmeiras','1-0'),
 ('CWC','FIFA Club World Cup','2008','LDU Quito','1-0');

-- 커뮤니티 실드 21회 (* 공동 우승 포함)
INSERT OR IGNORE INTO honours (competition_code, competition_name, season, note) VALUES
 ('CS','Community Shield','1908',NULL),('CS','Community Shield','1911',NULL),
 ('CS','Community Shield','1952',NULL),('CS','Community Shield','1956',NULL),
 ('CS','Community Shield','1957',NULL),('CS','Community Shield','1965','shared'),
 ('CS','Community Shield','1967','shared'),('CS','Community Shield','1977','shared'),
 ('CS','Community Shield','1983',NULL),('CS','Community Shield','1990','shared'),
 ('CS','Community Shield','1993',NULL),('CS','Community Shield','1994',NULL),
 ('CS','Community Shield','1996',NULL),('CS','Community Shield','1997',NULL),
 ('CS','Community Shield','2003',NULL),('CS','Community Shield','2007',NULL),
 ('CS','Community Shield','2008',NULL),('CS','Community Shield','2010',NULL),
 ('CS','Community Shield','2011',NULL),('CS','Community Shield','2013',NULL),
 ('CS','Community Shield','2016',NULL);

-- 주요 감독 --------------------------------------------------------------
INSERT INTO managers (name, name_ko, nationality, start_date, end_date, is_caretaker, note) VALUES
 ('Ernest Mangnall','어니스트 맹널','England','1903','1912',0,'첫 리그 우승'),
 ('Matt Busby','맷 버스비','Scotland','1945','1969',0,'버스비 베이브스, 1968 유러피언컵 (1970-71 재부임)'),
 ('Tommy Docherty','토미 도허티','Scotland','1972','1977',0,'1977 FA컵'),
 ('Ron Atkinson','론 앳킨슨','England','1981','1986',0,'FA컵 2회'),
 ('Alex Ferguson','알렉스 퍼거슨','Scotland','1986-11-06','2013-05-19',0,'리그 13회, 챔스 2회'),
 ('David Moyes','데이비드 모이스','Scotland','2013-07-01','2014-04-22',0,NULL),
 ('Louis van Gaal','루이 판할','Netherlands','2014-07','2016-05',0,'2016 FA컵'),
 ('José Mourinho','조제 모리뉴','Portugal','2016-05','2018-12',0,'2017 리그컵·유로파리그'),
 ('Ole Gunnar Solskjær','올레 군나르 솔샤르','Norway','2018-12','2021-11',0,NULL),
 ('Ralf Rangnick','랄프 랑닉','Germany','2021-12','2022-05',1,'임시 감독'),
 ('Erik ten Hag','에릭 텐하흐','Netherlands','2022-05','2024-10',0,'2023 리그컵, 2024 FA컵'),
 ('Ruben Amorim','후벵 아모링','Portugal','2024-11',NULL,0,'end_date: 현 상태 확인 후 갱신 필요');

-- 감독 영문 비고 (웹 본문용)
UPDATE managers SET note_en='First league title' WHERE name='Ernest Mangnall';
UPDATE managers SET note_en='Busby Babes, 1968 European Cup (returned 1970-71)' WHERE name='Matt Busby';
UPDATE managers SET note_en='1977 FA Cup' WHERE name='Tommy Docherty';
UPDATE managers SET note_en='Two FA Cups' WHERE name='Ron Atkinson';
UPDATE managers SET note_en='13 league titles, 2 Champions Leagues' WHERE name='Alex Ferguson';
UPDATE managers SET note_en='2016 FA Cup' WHERE name='Louis van Gaal';
UPDATE managers SET note_en='2017 League Cup & Europa League' WHERE name='José Mourinho';
UPDATE managers SET note_en='Interim manager' WHERE name='Ralf Rangnick';
UPDATE managers SET note_en='2023 League Cup, 2024 FA Cup' WHERE name='Erik ten Hag';

-- 역사 타임라인 ------------------------------------------------------------
INSERT INTO history_timeline (year, date, title, title_ko, category, sort_order) VALUES
 (1878, NULL,         'Newton Heath LYR F.C. founded',        '뉴턴 히스 LYR FC 창단',                 'founding', 1),
 (1902, NULL,         'Renamed Manchester United',             '맨체스터 유나이티드로 개명',              'founding', 2),
 (1908, NULL,         'First league title',                    '첫 리그 우승 (1907-08)',                  'trophy',   3),
 (1910, '1910-02-19', 'Old Trafford opens',                    '올드 트래포드 개장',                      'stadium',  4),
 (1941, '1941-03-11', 'Old Trafford bombed in the Blitz',      '2차대전 폭격으로 올드 트래포드 파손',       'stadium',  5),
 (1945, NULL,         'Matt Busby appointed',                  '맷 버스비 감독 부임',                     'manager',  6),
 (1958, '1958-02-06', 'Munich air disaster',                   '뮌헨 비행기 참사',                        'tragedy',  7),
 (1968, '1968-05-29', 'European Cup winners',                  '잉글랜드 클럽 최초 유러피언컵 우승',        'trophy',   8),
 (1986, '1986-11-06', 'Alex Ferguson appointed',               '알렉스 퍼거슨 감독 부임',                  'manager',  9),
 (1993, NULL,         'First Premier League title',            '첫 프리미어리그 우승 (26년 만의 리그 우승)', 'trophy',  10),
 (1999, '1999-05-26', 'The Treble',                            '트레블 달성 (리그·FA컵·챔스)',             'trophy',  11),
 (2008, '2008-05-21', 'Champions League winners in Moscow',    '모스크바 챔스 결승 승리',                  'trophy',  12),
 (2013, '2013-05-19', 'Ferguson retires after 20th title',     '20번째 리그 우승 후 퍼거슨 은퇴',           'manager', 13),
 (2017, '2017-05-24', 'Europa League winners',                 '유로파리그 우승',                         'trophy',  14),
 (2024, '2024-05-25', 'FA Cup winners vs Man City',            'FA컵 결승 맨시티전 승리 (13번째 FA컵)',     'trophy',  15);
