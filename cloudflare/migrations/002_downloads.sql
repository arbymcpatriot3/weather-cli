-- 002_downloads.sql
-- CleanShot D1 migration: download tracking
--
-- Apply with:
--   wrangler d1 execute cleanshot-db --file=cloudflare/migrations/002_downloads.sql

-- ── downloads ─────────────────────────────────────────────────────────────────
-- One row per download event. IP is hashed for privacy.
CREATE TABLE IF NOT EXISTS downloads (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  filename      TEXT    NOT NULL,
  downloaded_at INTEGER NOT NULL,
  ip_hash       TEXT,                    -- first 16 hex chars of SHA-256(ip)
  user_agent    TEXT,
  version       TEXT
);

-- ── download_stats ────────────────────────────────────────────────────────────
-- Running total per filename. Updated atomically with each download.
CREATE TABLE IF NOT EXISTS download_stats (
  filename         TEXT    PRIMARY KEY,
  total_downloads  INTEGER DEFAULT 0,
  last_downloaded  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_downloads_filename ON downloads(filename);
CREATE INDEX IF NOT EXISTS idx_downloads_at       ON downloads(downloaded_at);
