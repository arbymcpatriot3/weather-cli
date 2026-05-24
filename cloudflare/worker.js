/**
 * CleanShot License & User API
 * Cloudflare Worker — deploy with: wrangler deploy
 *
 * Endpoints:
 *   POST /v1/register        — new user signup
 *   GET  /v1/license         — app calls on every launch
 *   POST /v1/extend          — admin: extend a trial
 *   GET  /v1/admin/users     — admin: list all users
 *   POST /v1/admin/block     — admin: block a machine
 */

const ADMIN_KEY = "REPLACE_WITH_YOUR_ADMIN_SECRET"; // set via wrangler secret

// ── CORS headers ─────────────────────────────────────────────────────────────
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Admin-Key",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

function err(msg, status = 400) {
  return json({ error: msg }, status);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function nowSec() {
  return Math.floor(Date.now() / 1000);
}

function daysFromNow(days) {
  return nowSec() + days * 86400;
}

function randomKey(prefix = "cs") {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let key = prefix.toUpperCase() + "-";
  for (let i = 0; i < 4; i++) {
    for (let j = 0; j < 4; j++) {
      key += chars[Math.floor(Math.random() * chars.length)];
    }
    if (i < 3) key += "-";
  }
  return key; // e.g. CS-A3K9-MNPQ-XYZR-7B2W
}

function isAdminAuthorized(request) {
  return request.headers.get("X-Admin-Key") === ADMIN_KEY;
}

// ── Route handler ─────────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (method === "OPTIONS") {
      return new Response(null, { headers: CORS });
    }

    // ── POST /v1/register ────────────────────────────────────────────────────
    if (path === "/v1/register" && method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body?.email || !body?.machine_id) {
        return err("email and machine_id are required");
      }

      const { email, machine_id, name = "" } = body;

      // Check if this machine already has a trial record
      const existingMachine = await env.DB.prepare(
        "SELECT machine_id, first_email, trial_end, blocked FROM machine_trials WHERE machine_id = ?"
      ).bind(machine_id).first();

      if (existingMachine) {
        if (existingMachine.blocked) {
          return json({ status: "blocked", message: "This device is not eligible for a trial." }, 403);
        }
        // Machine already trialed — return existing license key
        const existingLicense = await env.DB.prepare(
          "SELECT key, type, expires_at FROM licenses WHERE machine_id = ? ORDER BY rowid DESC LIMIT 1"
        ).bind(machine_id).first();

        if (existingLicense && existingLicense.expires_at > nowSec()) {
          return json({
            status: "existing_trial",
            license_key: existingLicense.key,
            expires_at: existingLicense.expires_at,
            message: "A trial for this device already exists.",
          });
        }
        return json({ status: "trial_expired", message: "Trial has expired. Please subscribe." }, 403);
      }

      // Check if email already used (secondary check)
      const existingEmail = await env.DB.prepare(
        "SELECT id FROM users WHERE email = ?"
      ).bind(email).first();

      if (existingEmail) {
        return json({ status: "email_exists", message: "An account with this email already exists." }, 409);
      }

      // Create new user + trial
      const userId = crypto.randomUUID();
      const licenseKey = randomKey("CS");
      const trialEnd = daysFromNow(30);
      const now = nowSec();

      await env.DB.batch([
        env.DB.prepare(
          "INSERT INTO users (id, email, name, created_at, role) VALUES (?, ?, ?, ?, 'user')"
        ).bind(userId, email, name, now),

        env.DB.prepare(
          "INSERT INTO licenses (key, user_id, machine_id, type, expires_at, active) VALUES (?, ?, ?, 'trial', ?, 1)"
        ).bind(licenseKey, userId, machine_id, trialEnd),

        env.DB.prepare(
          "INSERT INTO machine_trials (machine_id, first_email, trial_start, trial_end, blocked) VALUES (?, ?, ?, ?, 0)"
        ).bind(machine_id, email, now, trialEnd),
      ]);

      return json({
        status: "registered",
        license_key: licenseKey,
        type: "trial",
        expires_at: trialEnd,
        days_remaining: 30,
        message: "Welcome to CleanShot! Your 30-day trial has started.",
      }, 201);
    }

    // ── GET /v1/license ──────────────────────────────────────────────────────
    if (path === "/v1/license" && method === "GET") {
      const licenseKey = url.searchParams.get("key");
      const machineId  = url.searchParams.get("machine");

      if (!licenseKey || !machineId) {
        return err("key and machine parameters are required");
      }

      // Check machine block first
      const machineRecord = await env.DB.prepare(
        "SELECT blocked FROM machine_trials WHERE machine_id = ?"
      ).bind(machineId).first();

      if (machineRecord?.blocked) {
        return json({ status: "blocked", allowed: false, message: "This device has been blocked." }, 403);
      }

      const license = await env.DB.prepare(
        `SELECT l.key, l.type, l.expires_at, l.active, l.machine_id,
                u.email, u.name, u.role
         FROM licenses l
         JOIN users u ON l.user_id = u.id
         WHERE l.key = ?`
      ).bind(licenseKey).first();

      if (!license) {
        return json({ status: "invalid", allowed: false, message: "License key not found." }, 404);
      }

      if (!license.active) {
        return json({ status: "revoked", allowed: false, message: "This license has been revoked." }, 403);
      }

      // Verify machine ID matches
      if (license.machine_id && license.machine_id !== machineId) {
        return json({ status: "machine_mismatch", allowed: false,
          message: "License is registered to a different device." }, 403);
      }

      const now = nowSec();
      const daysLeft = Math.max(0, Math.floor((license.expires_at - now) / 86400));

      if (license.type === "subscription") {
        return json({
          status: "active",
          allowed: true,
          type: "subscription",
          days_remaining: null,
          email: license.email,
        });
      }

      if (license.type === "tester") {
        return json({
          status: "active",
          allowed: true,
          type: "tester",
          days_remaining: daysLeft,
          expires_at: license.expires_at,
          email: license.email,
        });
      }

      // Trial
      if (now > license.expires_at) {
        return json({
          status: "expired",
          allowed: false,
          type: "trial",
          days_remaining: 0,
          message: "Your trial has expired. Visit cleanshothq.com to subscribe.",
        }, 402);
      }

      return json({
        status: "trial",
        allowed: true,
        type: "trial",
        days_remaining: daysLeft,
        expires_at: license.expires_at,
        email: license.email,
        message: daysLeft <= 5 ? `⚠ Trial expires in ${daysLeft} day(s). Subscribe at cleanshothq.com` : null,
      });
    }

    // ── POST /v1/extend (admin) ──────────────────────────────────────────────
    if (path === "/v1/extend" && method === "POST") {
      if (!isAdminAuthorized(request)) return err("Unauthorized", 401);

      const body = await request.json().catch(() => null);
      if (!body?.license_key || !body?.days) return err("license_key and days required");

      const newExpiry = daysFromNow(body.days);

      const result = await env.DB.prepare(
        "UPDATE licenses SET expires_at = ?, type = CASE WHEN type = 'trial' THEN 'tester' ELSE type END WHERE key = ?"
      ).bind(newExpiry, body.license_key).run();

      if (result.changes === 0) return err("License key not found", 404);

      // Also update machine_trials
      await env.DB.prepare(
        "UPDATE machine_trials SET trial_end = ? WHERE machine_id = (SELECT machine_id FROM licenses WHERE key = ?)"
      ).bind(newExpiry, body.license_key).run();

      return json({ status: "extended", license_key: body.license_key,
        new_expires_at: newExpiry, days_added: body.days });
    }

    // ── GET /v1/admin/users (admin) ──────────────────────────────────────────
    if (path === "/v1/admin/users" && method === "GET") {
      if (!isAdminAuthorized(request)) return err("Unauthorized", 401);

      const { results } = await env.DB.prepare(
        `SELECT u.email, u.name, u.role, u.created_at,
                l.key as license_key, l.type, l.expires_at, l.active,
                mt.blocked
         FROM users u
         LEFT JOIN licenses l ON l.user_id = u.id
         LEFT JOIN machine_trials mt ON mt.first_email = u.email
         ORDER BY u.created_at DESC
         LIMIT 500`
      ).all();

      return json({ users: results, count: results.length });
    }

    // ── POST /v1/admin/block (admin) ─────────────────────────────────────────
    if (path === "/v1/admin/block" && method === "POST") {
      if (!isAdminAuthorized(request)) return err("Unauthorized", 401);

      const body = await request.json().catch(() => null);
      if (!body?.machine_id) return err("machine_id required");

      await env.DB.prepare(
        "UPDATE machine_trials SET blocked = 1 WHERE machine_id = ?"
      ).bind(body.machine_id).run();

      await env.DB.prepare(
        "UPDATE licenses SET active = 0 WHERE machine_id = ?"
      ).bind(body.machine_id).run();

      return json({ status: "blocked", machine_id: body.machine_id });
    }

    return err("Not found", 404);
  },
};
