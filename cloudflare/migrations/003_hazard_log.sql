-- 003_hazard_log.sql
-- CleanShot D1 migration: hazard + session tracking, rate limiting
--
-- Apply with:
--   wrangler d1 execute cleanshot-db --file=cloudflare/migrations/003_hazard_log.sql

-- ── hazard_log ────────────────────────────────────────────────────────────────
-- One row per hazard detected and shown to a driver.
CREATE TABLE IF NOT EXISTS hazard_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  license_key  TEXT    NOT NULL,
  hazard_type  TEXT    NOT NULL,  -- black_ice | bridge_freeze | fog | flood |
                                   --   diesel_gel | high_wind | mudslide | dot_incident
  severity     TEXT    NOT NULL,  -- low | moderate | high | critical
  state        TEXT,              -- 2-letter state code, e.g. "PA"
  route        TEXT,              -- e.g. "I-81" or "US-30"
  detected_at  INTEGER NOT NULL,
  lat          REAL,
  lon          REAL,
  acknowledged INTEGER DEFAULT 0  -- 1 = driver saw the alert
);

-- ── session_log ───────────────────────────────────────────────────────────────
-- One row per app session (opened → closed). Reported by the app on session end.
CREATE TABLE IF NOT EXISTS session_log (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  license_key       TEXT    NOT NULL,
  session_start     INTEGER NOT NULL,
  session_end       INTEGER,
  queries           INTEGER DEFAULT 0,
  hazards_detected  INTEGER DEFAULT 0,
  states_checked    TEXT,          -- JSON array, e.g. ["PA","NJ","MD"]
  miles_covered     REAL
);

-- ── rate_limits ───────────────────────────────────────────────────────────────
-- Sliding-window rate limiter for account recovery endpoints.
CREATE TABLE IF NOT EXISTS rate_limits (
  key          TEXT    PRIMARY KEY,  -- e.g. "recover:user@example.com"
  count        INTEGER DEFAULT 0,
  window_start INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hazard_log_key        ON hazard_log(license_key);
CREATE INDEX IF NOT EXISTS idx_hazard_log_detected   ON hazard_log(detected_at);
CREATE INDEX IF NOT EXISTS idx_hazard_log_type       ON hazard_log(hazard_type);
CREATE INDEX IF NOT EXISTS idx_session_log_key       ON session_log(license_key);
