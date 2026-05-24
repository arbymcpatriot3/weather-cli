-- CleanShot D1 Database Schema
-- Run with: wrangler d1 execute cleanshot-db --file=schema.sql

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT DEFAULT '',
    created_at  INTEGER NOT NULL,
    role        TEXT DEFAULT 'user'   -- 'user', 'tester', 'admin'
);

-- Licenses table
CREATE TABLE IF NOT EXISTS licenses (
    key         TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    machine_id  TEXT,                 -- bound to device on first check
    type        TEXT NOT NULL,        -- 'trial', 'tester', 'subscription'
    expires_at  INTEGER,              -- NULL = never expires (subscription)
    active      INTEGER DEFAULT 1,    -- 0 = revoked
    created_at  INTEGER DEFAULT (unixepoch())
);

-- Machine trial tracking — the anti-bypass table
-- One row per physical machine. Survives email changes.
CREATE TABLE IF NOT EXISTS machine_trials (
    machine_id   TEXT PRIMARY KEY,
    first_email  TEXT NOT NULL,
    trial_start  INTEGER NOT NULL,
    trial_end    INTEGER NOT NULL,
    blocked      INTEGER DEFAULT 0    -- 1 = banned device
);

-- Subscriptions (Stripe webhook will populate this)
CREATE TABLE IF NOT EXISTS subscriptions (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL REFERENCES users(id),
    stripe_subscription_id  TEXT UNIQUE,
    stripe_customer_id      TEXT,
    status                  TEXT,     -- 'active', 'canceled', 'past_due'
    current_period_end      INTEGER,
    created_at              INTEGER DEFAULT (unixepoch())
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_licenses_user_id    ON licenses(user_id);
CREATE INDEX IF NOT EXISTS idx_licenses_machine_id ON licenses(machine_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user  ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_users_email         ON users(email);
