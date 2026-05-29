-- 001_referrals.sql
-- CleanShot D1 migration: referral tracking + discount management
--
-- Apply with:
--   wrangler d1 execute cleanshot-db --file=cloudflare/migrations/001_referrals.sql
--
-- This migration is idempotent (all statements use IF NOT EXISTS).

-- ── referrals ──────────────────────────────────────────────────────────────────
-- One row per referral code. Created when a subscriber generates their code.
-- Status lifecycle: active → pending → used
--                   active → expired  (manual/cleanup)
CREATE TABLE IF NOT EXISTS referrals (
  id                  TEXT PRIMARY KEY,           -- UUID
  referrer_email      TEXT NOT NULL,              -- subscriber who owns the code
  referrer_stripe_id  TEXT,                       -- Stripe customer ID of referrer
  ref_code            TEXT UNIQUE NOT NULL,       -- e.g. "bruce-4x7k"
  referee_email       TEXT,                       -- who used it (null until confirmed)
  referee_stripe_id   TEXT,                       -- Stripe customer ID of referee
  status              TEXT DEFAULT 'active',      -- active | pending | used | expired
  created_at          INTEGER NOT NULL,
  activated_at        INTEGER                     -- unix ts when subscription confirmed
);

-- ── referral_discounts ─────────────────────────────────────────────────────────
-- One row per referrer. Tracks their running discount earned from referrals.
-- Updated by the stripe webhook on subscription.created / subscription.deleted.
-- Max discount: $5.00/mo (5 active referrals × $1.00).
CREATE TABLE IF NOT EXISTS referral_discounts (
  referrer_stripe_id      TEXT PRIMARY KEY,
  active_referral_count   INTEGER DEFAULT 0,
  monthly_discount_cents  INTEGER DEFAULT 0,      -- max 500 (= $5.00)
  coupon_id               TEXT,                   -- Stripe coupon currently applied
  last_updated            INTEGER
);

-- ── indexes ────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_referrals_ref_code        ON referrals(ref_code);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer_email  ON referrals(referrer_email);
CREATE INDEX IF NOT EXISTS idx_referrals_referee_stripe  ON referrals(referee_stripe_id);
