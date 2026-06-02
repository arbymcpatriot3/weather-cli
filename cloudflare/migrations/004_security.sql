-- Migration 004: Security tables + devices + user columns
-- Run with: wrangler d1 execute cleanshot-db --remote --file=cloudflare/migrations/004_security.sql

-- Add security columns to users table
ALTER TABLE users ADD COLUMN tier TEXT NOT NULL DEFAULT 'trial';
ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN device_limit INTEGER NOT NULL DEFAULT 2;

-- Trusted device registry
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_fingerprint TEXT NOT NULL,
  device_name TEXT NOT NULL DEFAULT 'Unknown Device',
  platform TEXT NOT NULL DEFAULT 'windows',
  trusted INTEGER NOT NULL DEFAULT 1,
  registered_at INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_user_fp ON devices(user_id, device_fingerprint);
CREATE INDEX IF NOT EXISTS idx_devices_user ON devices(user_id);

-- OTP codes
CREATE TABLE IF NOT EXISTS otp_codes (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  email TEXT NOT NULL,
  code TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'new_device',
  used INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  ip_address TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_otp_user ON otp_codes(user_id);
CREATE INDEX IF NOT EXISTS idx_otp_expires ON otp_codes(expires_at);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT,
  ip_address TEXT,
  geo_country TEXT,
  geo_region TEXT,
  geo_lat REAL,
  geo_lon REAL,
  user_agent TEXT,
  created_at INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_device ON sessions(device_id);

-- Security events audit log
CREATE TABLE IF NOT EXISTS security_events (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info',
  ip_address TEXT,
  device_id TEXT,
  device_fingerprint TEXT,
  geo_country TEXT,
  geo_region TEXT,
  details TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sec_events_user ON security_events(user_id);
CREATE INDEX IF NOT EXISTS idx_sec_events_type ON security_events(event_type);
CREATE INDEX IF NOT EXISTS idx_sec_events_created ON security_events(created_at);

-- Device blacklist
CREATE TABLE IF NOT EXISTS device_blacklist (
  fingerprint TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  banned_by TEXT DEFAULT 'system',
  banned_at INTEGER NOT NULL,
  notes TEXT
);
