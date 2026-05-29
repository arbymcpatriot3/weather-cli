/**
 * CleanShot License, Checkout & Referral API
 * Cloudflare Worker — deploy with: wrangler deploy
 *
 * Endpoints:
 *   POST /v1/register              — app trial signup
 *   GET  /v1/license               — app license check on every launch
 *   POST /v1/extend                — admin: extend a trial
 *   GET  /v1/admin/users           — admin: list all users
 *   POST /v1/admin/block           — admin: block a machine
 *   GET  /v1/road511/*             — proxy road511 (license-gated)
 *   POST /v1/checkout              — create Stripe Checkout Session
 *   POST /v1/referral/generate     — generate a referral code (requires license)
 *   GET  /v1/referral/status       — get referral stats (requires license)
 *   POST /v1/webhooks/stripe       — Stripe webhook handler
 *
 * Secrets (set via wrangler secret put):
 *   ADMIN_KEY             — X-Admin-Key header value
 *   STRIPE_SECRET_KEY     — sk_live_... or sk_test_...
 *   STRIPE_WEBHOOK_SECRET — whsec_...
 *   ROAD511_API_KEY       — r511_...
 */

// ── Known Stripe price IDs ────────────────────────────────────────────────────
const VALID_PRICES = new Set([
  "price_1Tag20LvqVzoe5iIHptcxad8",  // Founding Member   $4.99/mo
  "price_1TafmGLvqVzoe5iIoXWUIlwc",  // Owner-Op          $7.99/mo
  "price_1Tag0ZLvqVzoe5iIvp3SBZtc",  // Owner-Op          $69.99/yr
  "price_1TafsPLvqVzoe5iIGfygkAww",  // Small Fleet       $19.99/mo
  "price_1TafujLvqVzoe5iIVYwD6eUq",  // Small Fleet       $179.99/yr
  "price_1TafyzLvqVzoe5iITfG5kBsb",  // Mid Fleet         $49.99/mo
  "price_1Tag0ZLvqVzoe5iIvp3SBZtc",  // Mid Fleet         $449.99/yr (same ID — as configured)
]);

// ── CORS ──────────────────────────────────────────────────────────────────────
const CORS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Admin-Key, Authorization",
};

// ── Basic response helpers ────────────────────────────────────────────────────
function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

function err(msg, status = 400) {
  return json({ error: msg }, status);
}

// ── General helpers ───────────────────────────────────────────────────────────
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
    for (let j = 0; j < 4; j++) key += chars[Math.floor(Math.random() * chars.length)];
    if (i < 3) key += "-";
  }
  return key; // CS-A3K9-MNPQ-XYZR-7B2W
}

function isAdminAuthorized(request, env) {
  return request.headers.get("X-Admin-Key") === env.ADMIN_KEY;
}

function getLicenseKey(request) {
  const auth = request.headers.get("Authorization") || "";
  return auth.replace(/^Bearer\s+/i, "").trim();
}

// ── Stripe helpers ────────────────────────────────────────────────────────────

/**
 * Recursively flatten a nested object to Stripe's bracket-notation params.
 * { line_items: [{ price: "p", quantity: 1 }] }
 * → [["line_items[0][price]", "p"], ["line_items[0][quantity]", "1"]]
 */
function flattenParams(obj, prefix = "") {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    if (v === null || v === undefined) continue;
    const key = prefix ? `${prefix}[${k}]` : k;
    if (Array.isArray(v)) {
      v.forEach((item, i) => {
        if (item === null || item === undefined) return;
        if (typeof item === "object") {
          out.push(...flattenParams(item, `${key}[${i}]`));
        } else {
          out.push([`${key}[${i}]`, String(item)]);
        }
      });
    } else if (typeof v === "object") {
      out.push(...flattenParams(v, key));
    } else {
      out.push([key, String(v)]);
    }
  }
  return out;
}

function encodeStripeBody(params) {
  return flattenParams(params)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&");
}

async function stripePost(path, params, env) {
  const r = await fetch(`https://api.stripe.com/v1${path}`, {
    method: "POST",
    headers: {
      "Authorization": `Basic ${btoa(env.STRIPE_SECRET_KEY + ":")}`,
      "Content-Type":  "application/x-www-form-urlencoded",
      "Stripe-Version": "2024-04-10",
    },
    body: encodeStripeBody(params),
  });
  return r.json();
}

async function stripeGet(path, env) {
  const r = await fetch(`https://api.stripe.com/v1${path}`, {
    headers: {
      "Authorization": `Basic ${btoa(env.STRIPE_SECRET_KEY + ":")}`,
      "Stripe-Version": "2024-04-10",
    },
  });
  return r.json();
}

async function stripeDel(path, env) {
  await fetch(`https://api.stripe.com/v1${path}`, {
    method: "DELETE",
    headers: {
      "Authorization": `Basic ${btoa(env.STRIPE_SECRET_KEY + ":")}`,
      "Stripe-Version": "2024-04-10",
    },
  });
}

/**
 * Verify Stripe webhook signature.
 * Returns false if missing, malformed, or older than 5 minutes.
 */
async function verifyStripeWebhook(rawBody, sigHeader, secret) {
  if (!sigHeader || !secret) return false;

  const parts = {};
  for (const chunk of sigHeader.split(",")) {
    const [k, ...rest] = chunk.split("=");
    if (k) parts[k.trim()] = rest.join("=").trim();
  }
  const timestamp = parts.t;
  const v1        = parts.v1;
  if (!timestamp || !v1) return false;

  if (Math.abs(nowSec() - parseInt(timestamp, 10)) > 300) return false;

  const payload = `${timestamp}.${rawBody}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signed = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  const hex = Array.from(new Uint8Array(signed))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");

  return hex === v1;
}

// ── Referral helpers ──────────────────────────────────────────────────────────

/**
 * Generate a human-friendly referral code.
 * Format: {first-name-slug}-{4-random-chars}  e.g. "bruce-4x7k"
 */
function generateRefCode(name, email) {
  const raw = ((name || email || "user").split(/[\s@.]/)[0] || "user")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .slice(0, 12) || "user";

  const chars = "abcdefghjkmnpqrstuvwxyz23456789";
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  const suffix = Array.from(bytes).map(b => chars[b % chars.length]).join("");

  return `${raw}-${suffix}`;
}

/**
 * Resolve a license key from Authorization header.
 * Returns the license row or null.
 */
async function resolveLicense(request, env) {
  const key = getLicenseKey(request);
  if (!key) return null;
  return env.DB.prepare(
    `SELECT l.key, l.active, l.type, l.expires_at, u.email, u.name, u.id as user_id
     FROM licenses l JOIN users u ON l.user_id = u.id
     WHERE l.key = ?`
  ).bind(key).first();
}

function licenseIsValid(lic) {
  if (!lic || !lic.active) return false;
  if (lic.type === "trial" && nowSec() > lic.expires_at) return false;
  return true;
}

/**
 * Get or create the Stripe coupon for a given discount level.
 * Coupon IDs are deterministic: ref-disc-100 … ref-disc-500 (cents).
 */
async function ensureCoupon(discountCents, env) {
  const couponId = `ref-disc-${discountCents}`;
  // Fire-and-forget creation; Stripe returns error if it already exists — we ignore that.
  await stripePost("/coupons", {
    id:         couponId,
    amount_off: discountCents,
    currency:   "usd",
    duration:   "forever",
    name:       `Referral Discount ($${(discountCents / 100).toFixed(2)}/mo)`,
  }, env);
  return couponId;
}

/**
 * Apply or remove a referral discount on a referrer's active Stripe subscription.
 * delta: +1 when a new referee subscribes, -1 when a referee cancels.
 */
async function updateReferrerDiscount(referrerStripeId, delta, env) {
  if (!referrerStripeId) return;

  try {
    const current = await env.DB.prepare(
      "SELECT active_referral_count FROM referral_discounts WHERE referrer_stripe_id = ?"
    ).bind(referrerStripeId).first();

    const newCount     = Math.max(0, Math.min(5, (current?.active_referral_count ?? 0) + delta));
    const discountCents = newCount * 100; // $1 per referral, max $5

    // Find referrer's active Stripe subscription
    const subList  = await stripeGet(
      `/subscriptions?customer=${referrerStripeId}&status=active&limit=1`, env
    );
    const activeSub = subList.data?.[0];

    let couponId = null;

    if (discountCents > 0 && activeSub) {
      couponId = await ensureCoupon(discountCents, env);
      await stripePost(`/subscriptions/${activeSub.id}`, { coupon: couponId }, env);
    } else if (discountCents === 0 && activeSub?.discount) {
      await stripeDel(`/subscriptions/${activeSub.id}/discount`, env);
    }

    // Upsert referral_discounts
    await env.DB.prepare(
      `INSERT INTO referral_discounts
         (referrer_stripe_id, active_referral_count, monthly_discount_cents, coupon_id, last_updated)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(referrer_stripe_id) DO UPDATE SET
         active_referral_count  = excluded.active_referral_count,
         monthly_discount_cents = excluded.monthly_discount_cents,
         coupon_id              = excluded.coupon_id,
         last_updated           = excluded.last_updated`
    ).bind(referrerStripeId, newCount, discountCents, couponId, nowSec()).run();

  } catch (e) {
    // Never crash the webhook over a discount update failure — log and continue
    console.error("updateReferrerDiscount error:", e.message);
  }
}

/**
 * Upsert a Stripe subscription into D1.
 * Best-effort user linkage via stripe_customer_id.
 */
async function upsertSubscription(sub, env) {
  try {
    const existing = await env.DB.prepare(
      "SELECT id, user_id FROM subscriptions WHERE stripe_subscription_id = ?"
    ).bind(sub.id).first();

    let userId = existing?.user_id ?? null;

    if (!userId) {
      // Try to find user by customer ID
      const userSub = await env.DB.prepare(
        "SELECT user_id FROM subscriptions WHERE stripe_customer_id = ? LIMIT 1"
      ).bind(sub.customer).first();
      userId = userSub?.user_id ?? "stripe-managed";
    }

    await env.DB.prepare(
      `INSERT INTO subscriptions
         (id, user_id, stripe_subscription_id, stripe_customer_id, status, current_period_end, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(stripe_subscription_id) DO UPDATE SET
         status             = excluded.status,
         current_period_end = excluded.current_period_end`
    ).bind(
      existing?.id ?? crypto.randomUUID(),
      userId,
      sub.id,
      sub.customer,
      sub.status,
      sub.current_period_end ?? null,
      nowSec(),
    ).run();
  } catch (e) {
    console.error("upsertSubscription error:", e.message);
  }
}

// ── Route handler ─────────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    const url    = new URL(request.url);
    const path   = url.pathname;
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

      const existingMachine = await env.DB.prepare(
        "SELECT machine_id, first_email, trial_end, blocked FROM machine_trials WHERE machine_id = ?"
      ).bind(machine_id).first();

      if (existingMachine) {
        if (existingMachine.blocked) {
          return json({ status: "blocked", message: "This device is not eligible for a trial." }, 403);
        }
        const existingLicense = await env.DB.prepare(
          "SELECT key, type, expires_at FROM licenses WHERE machine_id = ? ORDER BY rowid DESC LIMIT 1"
        ).bind(machine_id).first();

        if (existingLicense && existingLicense.expires_at > nowSec()) {
          return json({
            status:      "existing_trial",
            license_key: existingLicense.key,
            expires_at:  existingLicense.expires_at,
            message:     "A trial for this device already exists.",
          });
        }
        return json({ status: "trial_expired", message: "Trial has expired. Please subscribe." }, 403);
      }

      const existingEmail = await env.DB.prepare(
        "SELECT id FROM users WHERE email = ?"
      ).bind(email).first();

      if (existingEmail) {
        return json({ status: "email_exists", message: "An account with this email already exists." }, 409);
      }

      const userId     = crypto.randomUUID();
      const licenseKey = randomKey("CS");
      const trialEnd   = daysFromNow(30);
      const now        = nowSec();

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
        status:      "registered",
        license_key: licenseKey,
        type:        "trial",
        expires_at:  trialEnd,
        days_remaining: 30,
        message:     "Welcome to CleanShot! Your 30-day trial has started.",
      }, 201);
    }

    // ── GET /v1/license ──────────────────────────────────────────────────────
    if (path === "/v1/license" && method === "GET") {
      const licenseKey = url.searchParams.get("key");
      const machineId  = url.searchParams.get("machine");

      if (!licenseKey || !machineId) {
        return err("key and machine parameters are required");
      }

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

      if (!license)        return json({ status: "invalid",  allowed: false, message: "License key not found." }, 404);
      if (!license.active) return json({ status: "revoked",  allowed: false, message: "This license has been revoked." }, 403);

      if (license.machine_id && license.machine_id !== machineId) {
        return json({ status: "machine_mismatch", allowed: false,
          message: "License is registered to a different device." }, 403);
      }

      const now      = nowSec();
      const daysLeft = Math.max(0, Math.floor((license.expires_at - now) / 86400));

      if (license.type === "subscription") {
        return json({ status: "active", allowed: true, type: "subscription",
          days_remaining: null, email: license.email });
      }

      if (license.type === "tester") {
        return json({ status: "active", allowed: true, type: "tester",
          days_remaining: daysLeft, expires_at: license.expires_at, email: license.email });
      }

      // Trial
      if (now > license.expires_at) {
        return json({ status: "expired", allowed: false, type: "trial",
          days_remaining: 0,
          message: "Your trial has expired. Visit cleanshothq.com to subscribe." }, 402);
      }

      return json({
        status: "trial", allowed: true, type: "trial",
        days_remaining: daysLeft, expires_at: license.expires_at, email: license.email,
        message: daysLeft <= 5
          ? `⚠ Trial expires in ${daysLeft} day(s). Subscribe at cleanshothq.com`
          : null,
      });
    }

    // ── POST /v1/extend (admin) ──────────────────────────────────────────────
    if (path === "/v1/extend" && method === "POST") {
      if (!isAdminAuthorized(request, env)) return err("Unauthorized", 401);

      const body = await request.json().catch(() => null);
      if (!body?.license_key || !body?.days) return err("license_key and days required");

      const newExpiry = daysFromNow(body.days);
      const result    = await env.DB.prepare(
        "UPDATE licenses SET expires_at = ?, type = CASE WHEN type = 'trial' THEN 'tester' ELSE type END WHERE key = ?"
      ).bind(newExpiry, body.license_key).run();

      if (result.changes === 0) return err("License key not found", 404);

      await env.DB.prepare(
        "UPDATE machine_trials SET trial_end = ? WHERE machine_id = (SELECT machine_id FROM licenses WHERE key = ?)"
      ).bind(newExpiry, body.license_key).run();

      return json({ status: "extended", license_key: body.license_key,
        new_expires_at: newExpiry, days_added: body.days });
    }

    // ── GET /v1/admin/users (admin) ──────────────────────────────────────────
    if (path === "/v1/admin/users" && method === "GET") {
      if (!isAdminAuthorized(request, env)) return err("Unauthorized", 401);

      const { results } = await env.DB.prepare(
        `SELECT u.email, u.name, u.role, u.created_at,
                l.key as license_key, l.type, l.expires_at, l.active,
                mt.blocked,
                s.stripe_customer_id, s.status as sub_status,
                rd.active_referral_count, rd.monthly_discount_cents
         FROM users u
         LEFT JOIN licenses l        ON l.user_id = u.id
         LEFT JOIN machine_trials mt ON mt.first_email = u.email
         LEFT JOIN subscriptions s   ON s.user_id = u.id
         LEFT JOIN referral_discounts rd ON rd.referrer_stripe_id = s.stripe_customer_id
         ORDER BY u.created_at DESC
         LIMIT 500`
      ).all();

      return json({ users: results, count: results.length });
    }

    // ── POST /v1/admin/block (admin) ─────────────────────────────────────────
    if (path === "/v1/admin/block" && method === "POST") {
      if (!isAdminAuthorized(request, env)) return err("Unauthorized", 401);

      const body = await request.json().catch(() => null);
      if (!body?.machine_id) return err("machine_id required");

      await env.DB.prepare("UPDATE machine_trials SET blocked = 1 WHERE machine_id = ?")
        .bind(body.machine_id).run();
      await env.DB.prepare("UPDATE licenses SET active = 0 WHERE machine_id = ?")
        .bind(body.machine_id).run();

      return json({ status: "blocked", machine_id: body.machine_id });
    }

    // ── GET /v1/road511/* ────────────────────────────────────────────────────
    // Proxy to road511 — license validated server-side, API key never in binary.
    if (path.startsWith("/v1/road511/") && method === "GET") {
      const licenseKey = url.searchParams.get("license_key");
      const machineId  = url.searchParams.get("machine_id");

      if (!licenseKey || !machineId) return err("license_key and machine_id required", 401);

      const machineRecord = await env.DB.prepare(
        "SELECT blocked FROM machine_trials WHERE machine_id = ?"
      ).bind(machineId).first();
      if (machineRecord?.blocked) return json({ error: "blocked", allowed: false }, 403);

      const license = await env.DB.prepare(
        "SELECT l.key, l.type, l.expires_at, l.active FROM licenses l WHERE l.key = ? AND l.machine_id = ?"
      ).bind(licenseKey, machineId).first();

      if (!license || !license.active) return err("license invalid or revoked", 403);
      if (license.type === "trial" && nowSec() > license.expires_at) {
        return err("trial expired — subscribe at cleanshothq.com", 402);
      }

      const r511Params = new URLSearchParams(url.searchParams);
      r511Params.delete("license_key");
      r511Params.delete("machine_id");

      const r511Path = path.replace("/v1/road511", "");
      const r511Url  = `https://api.road511.com/api/v1${r511Path}?${r511Params.toString()}`;

      try {
        const upstream = await fetch(r511Url, {
          headers: {
            "X-API-Key":  env.ROAD511_API_KEY,
            "User-Agent": "clean-shot/3.0 (cleanshothq@pm.me)",
            "Accept":     "application/json",
          },
        });
        const data = await upstream.json().catch(() => ({}));
        return json(data, upstream.status);
      } catch (e) {
        return err(`road511 upstream error: ${e.message}`, 502);
      }
    }

    // ── POST /v1/checkout ────────────────────────────────────────────────────
    // Create a Stripe Checkout Session. Frontend redirects to checkout_url.
    if (path === "/v1/checkout" && method === "POST") {
      const body = await request.json().catch(() => null);

      if (!body?.price_id) return err("price_id is required");
      if (!VALID_PRICES.has(body.price_id)) return err("unknown price_id", 400);

      const successUrl = body.success_url || "https://cleanshothq.com/success";
      const cancelUrl  = body.cancel_url  || "https://cleanshothq.com/#pricing";
      const refCode    = (body.ref_code || "").trim();

      // Validate ref_code: exists, active, referrer is active subscriber
      let validReferral = null;
      if (refCode) {
        const referral = await env.DB.prepare(
          "SELECT * FROM referrals WHERE ref_code = ? AND status = 'active'"
        ).bind(refCode).first();

        if (referral) {
          // Verify referrer has an active Stripe subscription
          const refSub = referral.referrer_stripe_id
            ? await env.DB.prepare(
                "SELECT status FROM subscriptions WHERE stripe_customer_id = ? AND status = 'active' LIMIT 1"
              ).bind(referral.referrer_stripe_id).first()
            : null;

          if (refSub) {
            validReferral = referral;
          }
          // Invalid referrer: proceed without referral credit, don't surface the error
        }
      }

      // Build Stripe Checkout Session params
      const sessionParams = {
        mode: "subscription",
        success_url: successUrl,
        cancel_url:  cancelUrl,
        allow_promotion_codes: false,
        line_items: [{ price: body.price_id, quantity: 1 }],
        subscription_data: {
          trial_period_days: 30,
          metadata: {
            ref_code: validReferral ? refCode : "",
            source:   "website",
          },
        },
        metadata: {
          ref_code: validReferral ? refCode : "",
          source:   "website",
        },
      };

      const session = await stripePost("/checkout/sessions", sessionParams, env);

      if (!session.url) {
        const msg = session.error?.message || "Stripe checkout unavailable";
        return err(msg, 502);
      }

      // Mark referral as pending so it can't be reused during this checkout
      if (validReferral) {
        await env.DB.prepare(
          "UPDATE referrals SET status = 'pending' WHERE ref_code = ?"
        ).bind(refCode).run();
      }

      return json({ checkout_url: session.url });
    }

    // ── POST /v1/referral/generate ───────────────────────────────────────────
    // Generate a referral code for the authenticated subscriber.
    if (path === "/v1/referral/generate" && method === "POST") {
      const lic = await resolveLicense(request, env);
      if (!lic) return err("Authorization: Bearer <license_key> required", 401);
      if (!licenseIsValid(lic)) return err("license expired or revoked", 403);

      // Return existing code if one already exists
      const existing = await env.DB.prepare(
        "SELECT ref_code FROM referrals WHERE referrer_email = ? AND status != 'expired' LIMIT 1"
      ).bind(lic.email).first();

      if (existing) {
        return json({
          ref_code:     existing.ref_code,
          referral_url: `https://cleanshothq.com/?ref=${existing.ref_code}`,
        });
      }

      // Look up Stripe customer ID (may be null for trial users)
      const sub = await env.DB.prepare(
        `SELECT s.stripe_customer_id
         FROM subscriptions s
         WHERE s.user_id = ? AND s.status = 'active'
         LIMIT 1`
      ).bind(lic.user_id).first();

      // Generate a unique ref_code (retry up to 5 times on collision)
      let refCode = null;
      for (let i = 0; i < 5; i++) {
        const candidate = generateRefCode(lic.name, lic.email);
        const collision = await env.DB.prepare(
          "SELECT 1 FROM referrals WHERE ref_code = ?"
        ).bind(candidate).first();
        if (!collision) { refCode = candidate; break; }
      }
      if (!refCode) return err("could not generate unique code — please try again", 500);

      await env.DB.prepare(
        `INSERT INTO referrals
           (id, referrer_email, referrer_stripe_id, ref_code, status, created_at)
         VALUES (?, ?, ?, ?, 'active', ?)`
      ).bind(
        crypto.randomUUID(),
        lic.email,
        sub?.stripe_customer_id ?? null,
        refCode,
        nowSec(),
      ).run();

      return json({
        ref_code:     refCode,
        referral_url: `https://cleanshothq.com/?ref=${refCode}`,
      }, 201);
    }

    // ── GET /v1/referral/status ──────────────────────────────────────────────
    // Return current referral code and discount stats.
    if (path === "/v1/referral/status" && method === "GET") {
      const lic = await resolveLicense(request, env);
      if (!lic) return err("Authorization: Bearer <license_key> required", 401);
      if (!licenseIsValid(lic)) return err("license expired or revoked", 403);

      const referral = await env.DB.prepare(
        "SELECT ref_code FROM referrals WHERE referrer_email = ? AND status != 'expired' LIMIT 1"
      ).bind(lic.email).first();

      if (!referral) {
        return json({
          ref_code:         null,
          referral_url:     null,
          active_referrals: 0,
          monthly_discount: "0.00",
          max_discount:     "5.00",
          message:          "No referral code yet. POST /v1/referral/generate to create one.",
        });
      }

      const sub = await env.DB.prepare(
        "SELECT stripe_customer_id FROM subscriptions WHERE user_id = ? AND status = 'active' LIMIT 1"
      ).bind(lic.user_id).first();

      const discount = sub?.stripe_customer_id
        ? await env.DB.prepare(
            "SELECT active_referral_count, monthly_discount_cents FROM referral_discounts WHERE referrer_stripe_id = ?"
          ).bind(sub.stripe_customer_id).first()
        : null;

      return json({
        ref_code:         referral.ref_code,
        referral_url:     `https://cleanshothq.com/?ref=${referral.ref_code}`,
        active_referrals: discount?.active_referral_count ?? 0,
        monthly_discount: ((discount?.monthly_discount_cents ?? 0) / 100).toFixed(2),
        max_discount:     "5.00",
      });
    }

    // ── POST /v1/webhooks/stripe ─────────────────────────────────────────────
    // Stripe sends signed events here. Verify signature before trusting any data.
    if (path === "/v1/webhooks/stripe" && method === "POST") {
      const rawBody = await request.text();
      const sigHeader = request.headers.get("Stripe-Signature") || "";

      const valid = await verifyStripeWebhook(rawBody, sigHeader, env.STRIPE_WEBHOOK_SECRET);
      if (!valid) return err("invalid webhook signature", 400);

      let event;
      try {
        event = JSON.parse(rawBody);
      } catch {
        return err("invalid JSON", 400);
      }

      const sub = event.data?.object;

      // ── customer.subscription.created ──────────────────────────────────────
      if (event.type === "customer.subscription.created") {
        await upsertSubscription(sub, env);

        const refCode = sub.metadata?.ref_code;
        if (refCode) {
          const referral = await env.DB.prepare(
            "SELECT * FROM referrals WHERE ref_code = ? AND status IN ('active', 'pending')"
          ).bind(refCode).first();

          if (referral) {
            // Get referee's email from Stripe to complete the record
            let refereeEmail = null;
            try {
              const customer = await stripeGet(`/customers/${sub.customer}`, env);
              refereeEmail = customer.email ?? null;
            } catch { /* best-effort */ }

            await env.DB.prepare(
              `UPDATE referrals
               SET status = 'used', referee_email = ?, referee_stripe_id = ?, activated_at = ?
               WHERE ref_code = ?`
            ).bind(refereeEmail, sub.customer, nowSec(), refCode).run();

            await updateReferrerDiscount(referral.referrer_stripe_id, +1, env);
          }
        }
      }

      // ── customer.subscription.updated ──────────────────────────────────────
      if (event.type === "customer.subscription.updated") {
        await upsertSubscription(sub, env);
      }

      // ── customer.subscription.deleted ──────────────────────────────────────
      if (event.type === "customer.subscription.deleted") {
        // Update subscription record
        await env.DB.prepare(
          "UPDATE subscriptions SET status = 'canceled' WHERE stripe_subscription_id = ?"
        ).bind(sub.id).run();

        // Was this customer a referee? If so, remove the referrer's credit.
        const referral = await env.DB.prepare(
          "SELECT referrer_stripe_id FROM referrals WHERE referee_stripe_id = ? AND status = 'used'"
        ).bind(sub.customer).first();

        if (referral?.referrer_stripe_id) {
          await updateReferrerDiscount(referral.referrer_stripe_id, -1, env);
        }
      }

      return json({ received: true });
    }

    return err("Not found", 404);
  },
};
