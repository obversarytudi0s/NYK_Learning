-- In SQLite: sqlite3 -header -column path/to/knicks.sqlite < sql/analysis.sql
SELECT * FROM season_summary ORDER BY season, season_type;
SELECT season, season_type, venue_side, COUNT(*) games,
       ROUND(100.0 * SUM(wl='W') / COUNT(*), 2) win_pct,
       ROUND(AVG(pts), 2) points_per_game
FROM team_games GROUP BY season, season_type, venue_side;

-- Prior five games only: excludes today's result for pre-game feature generation.
SELECT season, season_type, game_id, game_date, pts,
       COUNT(*) OVER (
         PARTITION BY season, season_type ORDER BY game_date, game_id
         ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
       ) AS history_games,
       AVG(pts) OVER (
         PARTITION BY season, season_type ORDER BY game_date, game_id
         ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
       ) AS prior_5_points
FROM team_games ORDER BY season, season_type, game_date, game_id;
