/**
 * CleanShot API — License, Checkout, Referral, Dashboard & Download
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
 *   GET  /download/CleanShot.exe   — serve signed exe from R2 + log download
 *   POST /v1/account/login         — dashboard login (email + license key → JWT)
 *   GET  /v1/account/me            — dashboard: full account info (JWT)
 *   GET  /v1/account/stats         — dashboard: usage stats (JWT)
 *   POST /v1/account/logout        — dashboard: invalidate session (client-side)
 *   POST /v1/billing/portal        — Stripe Customer Portal URL (JWT)
 *   POST /v1/account/recover       — forgot license key → email recovery
 *   POST /v1/account/resend-welcome — resend welcome (Stripe last4 verification)
 *   POST /v1/hazard/log            — app reports a detected hazard (X-License-Key)
 *   POST /v1/session/log           — app reports session summary (X-License-Key)
 *
 * Secrets (set via wrangler secret put):
 *   ADMIN_KEY              — X-Admin-Key header value
 *   STRIPE_SECRET_KEY      — sk_live_... or sk_test_...
 *   STRIPE_WEBHOOK_SECRET  — whsec_...
 *   R511_API_KEY           — r511_...
 *   JWT_SECRET             — long random string for signing dashboard tokens
 *   MAILCHANNELS_API_KEY   — MailChannels API key (optional; required if domain SPF not set)
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
  "Access-Control-Allow-Headers": "Content-Type, X-Admin-Key, Authorization, X-License-Key",
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

// ── JWT helpers ───────────────────────────────────────────────────────────────
// Tokens expire in 30 days. Signed with HMAC-SHA256 using env.JWT_SECRET.

function _b64url(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function _bytesToB64url(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function _b64urlToStr(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return atob(s);
}

async function signJWT(payload, secret) {
  const header = _b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body   = _b64url(JSON.stringify(payload));
  const msg    = `${header}.${body}`;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return `${msg}.${_bytesToB64url(new Uint8Array(sig))}`;
}

async function verifyJWT(token, secret) {
  if (!token || !secret) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [header, body, sig] = parts;
  const msg = `${header}.${body}`;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["verify"]
  );
  let sigPad = sig.replace(/-/g, "+").replace(/_/g, "/");
  while (sigPad.length % 4) sigPad += "=";
  const sigBytes = Uint8Array.from(atob(sigPad), c => c.charCodeAt(0));
  const valid = await crypto.subtle.verify("HMAC", key, sigBytes, new TextEncoder().encode(msg));
  if (!valid) return null;
  try {
    const payload = JSON.parse(_b64urlToStr(body));
    if (payload.exp && nowSec() > payload.exp) return null;
    return payload;
  } catch { return null; }
}

async function requireJWT(request, env) {
  const token = getLicenseKey(request);
  if (!token) return null;
  return verifyJWT(token, env.JWT_SECRET);
}

// ── Account helpers ───────────────────────────────────────────────────────────

function getXLicenseKey(request) {
  return (request.headers.get("X-License-Key") || "").trim();
}

/**
 * D1-backed sliding-window rate limiter.
 * Returns true if the request is allowed, false if rate-limited.
 */
async function checkRateLimit(key, maxCount, windowSecs, env) {
  const now = nowSec();
  try {
    const row = await env.DB.prepare(
      "SELECT count, window_start FROM rate_limits WHERE key = ?"
    ).bind(key).first();

    if (!row || (now - row.window_start) >= windowSecs) {
      await env.DB.prepare(
        `INSERT INTO rate_limits (key, count, window_start) VALUES (?, 1, ?)
         ON CONFLICT(key) DO UPDATE SET count = 1, window_start = excluded.window_start`
      ).bind(key, now).run();
      return true;
    }

    if (row.count >= maxCount) return false;

    await env.DB.prepare(
      "UPDATE rate_limits SET count = count + 1 WHERE key = ?"
    ).bind(key).run();
    return true;
  } catch { return true; } // fail open — never block on a DB error
}

/**
 * Send an email via MailChannels transactional API.
 * Requires SPF record "include:relay.mailchannels.net" on your domain,
 * OR set MAILCHANNELS_API_KEY secret for authenticated sends.
 */
async function sendEmail(to, subject, htmlBody, textBody, env) {
  const headers = { "Content-Type": "application/json" };
  if (env.MAILCHANNELS_API_KEY) headers["X-Auth-API-Key"] = env.MAILCHANNELS_API_KEY;

  try {
    await fetch("https://api.mailchannels.net/tx/v1/send", {
      method: "POST",
      headers,
      body: JSON.stringify({
        personalizations: [{ to: [{ email: to }] }],
        from: { email: "support@cleanshothq.com", name: "CleanShot HQ" },
        subject,
        content: [
          { type: "text/plain", value: textBody },
          { type: "text/html",  value: htmlBody },
        ],
      }),
    });
  } catch (e) {
    console.error("sendEmail error:", e.message);
  }
}

function buildWelcomeEmail(name, planName, licenseKey, refCode, refUrl, isTrialActive) {
  const greeting  = name || "Fellow Trucker";
  const trialNote = isTrialActive ? "Your 30-day free trial is active — no charge until it ends. " : "";
  const refSection = refCode ? `
    <tr>
      <td style="padding:24px 32px;border-bottom:1px solid #2a3040;background:#0f1a0f;">
        <div style="font-size:0.75rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#2ecc71;margin-bottom:10px;">🤝 Your Referral Code</div>
        <p style="margin:0 0 10px;font-size:0.88rem;color:#8892a4;line-height:1.6;">
          Share your link — earn <strong style="color:#e8eaf0;">$1/mo off</strong> per active subscriber, up to <strong style="color:#e8eaf0;">$5/mo</strong>.
        </p>
        <div style="background:#0d0f12;border:1px solid #2a4a1a;border-radius:6px;padding:12px;margin-bottom:8px;text-align:center;">
          <span style="font-family:monospace;font-size:1.1rem;font-weight:700;color:#2ecc71;letter-spacing:0.08em;">${refCode}</span>
        </div>
        <div style="text-align:center;font-size:0.85rem;">
          <a href="${refUrl}" style="color:#4a9eff;">${refUrl}</a>
        </div>
      </td>
    </tr>` : "";

  const html = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#0d0f12;font-family:'Segoe UI',Arial,sans-serif;color:#e8eaf0;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0f12;padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#161a1f;border:1px solid #2a3040;border-radius:12px;overflow:hidden;">
  <tr><td style="background:#0d0f12;border-bottom:1px solid #2a3040;padding:24px 32px;text-align:center;">
    <div style="font-size:1.3rem;font-weight:800;color:#f0a500;">⚡ CleanShot HQ</div>
    <div style="font-size:0.8rem;color:#8892a4;margin-top:4px;">Built for the road, not the boardroom.</div>
  </td></tr>
  <tr><td style="padding:32px 32px 24px;text-align:center;border-bottom:1px solid #2a3040;">
    <div style="font-size:0.75rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#f0a500;margin-bottom:8px;">Welcome aboard</div>
    <h1 style="margin:0 0 12px;font-size:1.6rem;font-weight:800;">Hey ${greeting} 👋</h1>
    <p style="margin:0;color:#8892a4;font-size:0.95rem;line-height:1.6;">
      Your <strong style="color:#e8eaf0;">${planName}</strong> account is ready. ${trialNote}Save this email — your license key is your password.
    </p>
  </td></tr>
  <tr><td style="padding:28px 32px;border-bottom:1px solid #2a3040;">
    <div style="font-size:0.75rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#8892a4;margin-bottom:10px;">Your License Key</div>
    <div style="background:#0d0f12;border:2px solid #f0a500;border-radius:8px;padding:16px;text-align:center;">
      <div style="font-family:monospace;font-size:1.4rem;font-weight:800;color:#f0a500;letter-spacing:0.12em;">${licenseKey}</div>
    </div>
    <p style="margin:10px 0 0;font-size:0.82rem;color:#8892a4;text-align:center;">Works on any device. Enter it at cleanshothq.com/dashboard to sign in.</p>
  </td></tr>
  <tr><td style="padding:28px 32px;border-bottom:1px solid #2a3040;">
    <div style="font-size:0.75rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#8892a4;margin-bottom:16px;">Get Started</div>
    <p style="margin:0 0 10px;font-size:0.9rem;">
      <strong>1.</strong> <a href="https://cleanshothq.com/download/CleanShot.exe" style="color:#4a9eff;">Download CleanShot.exe</a> — signed, no SmartScreen warnings
    </p>
    <p style="margin:0 0 10px;font-size:0.9rem;">
      <strong>2.</strong> Run it, enter your city or ZIP when prompted
    </p>
    <p style="margin:0;font-size:0.9rem;">
      <strong>3.</strong> <a href="https://cleanshothq.com/dashboard" style="color:#4a9eff;">Sign in to your dashboard</a> with your email + license key
    </p>
  </td></tr>
  ${refSection}
  <tr><td style="padding:24px 32px;border-bottom:1px solid #2a3040;">
    <div style="font-size:0.75rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#8892a4;margin-bottom:10px;">Need Help?</div>
    <p style="margin:0;font-size:0.88rem;color:#8892a4;line-height:1.7;">
      Email: <a href="mailto:support@cleanshothq.com" style="color:#f0a500;">support@cleanshothq.com</a><br>
      Phone: <a href="tel:6092021087" style="color:#f0a500;">(609) 202-1087</a> — we reply within 24 hours.
    </p>
  </td></tr>
  <tr><td style="padding:20px 32px;text-align:center;">
    <p style="margin:0;font-size:0.78rem;color:#555;line-height:1.8;">
      <strong style="color:#8892a4;">CleanShotHQ LLC</strong> • Salem, NJ 08079<br>
      No ads. Ever. <a href="https://cleanshothq.com" style="color:#555;">cleanshothq.com</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>`;

  const text = `Hey ${greeting},\n\nWelcome to CleanShot HQ! Your ${planName} account is ready.\n${trialNote}\n\nYOUR LICENSE KEY: ${licenseKey}\n\nSave this — it's your password on any device.\n\nGet started:\n1. Download: https://cleanshothq.com/download/CleanShot.exe\n2. Dashboard: https://cleanshothq.com/dashboard\n\n${refCode ? `Your referral code: ${refCode}\nShare: ${refUrl}\nEarn $1/mo off per active referral, up to $5/mo.\n\n` : ""}Need help? support@cleanshothq.com or (609) 202-1087\n\nCleanShotHQ LLC — Built for the road, not the boardroom.`;

  return { html, text };
}

function buildRecoveryEmail(name, licenseKey) {
  const greeting = name || "there";
  const html = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#0d0f12;font-family:'Segoe UI',Arial,sans-serif;color:#e8eaf0;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0f12;padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#161a1f;border:1px solid #2a3040;border-radius:12px;overflow:hidden;">
  <tr><td style="background:#0d0f12;border-bottom:1px solid #2a3040;padding:24px 32px;text-align:center;">
    <div style="font-size:1.3rem;font-weight:800;color:#f0a500;">⚡ CleanShot HQ</div>
  </td></tr>
  <tr><td style="padding:32px 32px 24px;text-align:center;border-bottom:1px solid #2a3040;">
    <h1 style="margin:0 0 12px;font-size:1.4rem;font-weight:800;">Your license key, ${greeting}</h1>
    <p style="margin:0;color:#8892a4;font-size:0.95rem;">You requested a reminder. Here it is.</p>
  </td></tr>
  <tr><td style="padding:28px 32px;border-bottom:1px solid #2a3040;">
    <div style="background:#0d0f12;border:2px solid #f0a500;border-radius:8px;padding:16px;text-align:center;">
      <div style="font-family:monospace;font-size:1.4rem;font-weight:800;color:#f0a500;letter-spacing:0.12em;">${licenseKey}</div>
    </div>
    <p style="margin:10px 0 0;font-size:0.82rem;color:#8892a4;text-align:center;">
      Sign in at <a href="https://cleanshothq.com/dashboard" style="color:#4a9eff;">cleanshothq.com/dashboard</a>
    </p>
  </td></tr>
  <tr><td style="padding:20px 32px;text-align:center;">
    <p style="margin:0;font-size:0.82rem;color:#555;">
      Didn't request this? Ignore it — your key was not changed.<br>
      Questions? <a href="mailto:support@cleanshothq.com" style="color:#8892a4;">support@cleanshothq.com</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>`;

  const text = `Hey ${greeting},\n\nYour CleanShot license key:\n\n${licenseKey}\n\nSign in: https://cleanshothq.com/dashboard\n\nDidn't request this? Ignore it — your key was not changed.\nQuestions? support@cleanshothq.com\n\nCleanShotHQ LLC`;

  return { html, text };
}

// ── Savings calculation constants ─────────────────────────────────────────────
const HAZARD_SAVINGS = {
  black_ice:     { fuel_gal: 0.8, time_min: 45 },
  bridge_freeze: { fuel_gal: 0.8, time_min: 45 },
  fog:           { fuel_gal: 0.4, time_min: 20 },
  flood:         { fuel_gal: 0.4, time_min: 20 },
  high_wind:     { fuel_gal: 0.3, time_min: 15 },
  diesel_gel:    { fuel_gal: 0.5, time_min: 30 },
  mudslide:      { fuel_gal: 0.6, time_min: 30 },
  dot_incident:  { fuel_gal: 0.4, time_min: 20 },
};
const DIESEL_PER_GAL      = 3.90;
const DRIVER_HOURLY_USD   = 25.00;
const DATA_COST_PER_MB    = 0.05;
const DATA_SAVED_MB_PER_MONTH = 99.5; // 100MB competitor - 0.5MB CleanShot
const DEFAULT_MONTHLY_SUB = 7.99;

function calcSavings(hazardRows, monthsActive) {
  const byType     = {};
  const bySeverity = { critical: 0, high: 0, moderate: 0, low: 0 };
  let fuelGal = 0;
  let timeMin = 0;

  for (const row of hazardRows) {
    byType[row.hazard_type] = (byType[row.hazard_type] || 0) + row.cnt;
    const sev = row.severity || "low";
    bySeverity[sev] = (bySeverity[sev] || 0) + row.cnt;
    const s = HAZARD_SAVINGS[row.hazard_type] || { fuel_gal: 0.4, time_min: 20 };
    fuelGal += s.fuel_gal * row.cnt;
    timeMin += s.time_min * row.cnt;
  }

  const totalHazards   = hazardRows.reduce((s, r) => s + r.cnt, 0);
  const fuelCostSaved  = parseFloat((fuelGal * DIESEL_PER_GAL).toFixed(2));
  const timeHours      = parseFloat((timeMin / 60).toFixed(1));
  const timeCostSaved  = parseFloat((timeHours * DRIVER_HOURLY_USD).toFixed(2));
  const dataSavedMb    = parseFloat((monthsActive * DATA_SAVED_MB_PER_MONTH).toFixed(1));
  const dataCostSaved  = parseFloat((dataSavedMb * DATA_COST_PER_MB).toFixed(2));
  const totalValue     = parseFloat((fuelCostSaved + timeCostSaved + dataCostSaved).toFixed(2));
  const totalPaid      = parseFloat((monthsActive * DEFAULT_MONTHLY_SUB).toFixed(2));
  const roi            = totalPaid > 0 ? parseFloat((totalValue / totalPaid).toFixed(1)) : 0;

  return {
    byType,
    bySeverity,
    totalHazards,
    fuelGal:      parseFloat(fuelGal.toFixed(2)),
    fuelCostSaved,
    timeHours,
    timeCostSaved,
    dataSavedMb,
    dataCostSaved,
    totalValue,
    totalPaid,
    roi,
  };
}

function _planName(licType, sub) {
  if (sub?.status === "active") return "Subscriber";
  if (licType === "tester")     return "Beta Tester";
  return "Free Trial";
}

function _accountStatus(user, sub) {
  if (!user.active)              return "revoked";
  if (sub?.status === "active")  return "active";
  if (user.type === "tester")    return "active";
  if (user.type === "trial") {
    return nowSec() > user.expires_at ? "expired" : "trial";
  }
  return "inactive";
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

    const newCount      = Math.max(0, Math.min(5, (current?.active_referral_count ?? 0) + delta));
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
  async fetch(request, env, ctx) {
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
            "X-API-Key":  env.R511_API_KEY,
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
      const rawBody   = await request.text();
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

        // Send welcome email (fire-and-forget, never block the webhook response)
        ctx.waitUntil((async () => {
          try {
            // Fetch subscriber details from Stripe
            const customer = await stripeGet(`/customers/${sub.customer}`, env);
            const toEmail  = customer.email;
            if (!toEmail) return;

            // Look up their license key from D1
            const subRow = await env.DB.prepare(
              "SELECT user_id FROM subscriptions WHERE stripe_customer_id = ? LIMIT 1"
            ).bind(sub.customer).first();

            let licenseKey = "";
            let userName   = customer.name || "";
            let refCode2   = "";
            let refUrl2    = "";

            if (subRow?.user_id) {
              const licRow = await env.DB.prepare(
                "SELECT key FROM licenses WHERE user_id = ? AND active = 1 ORDER BY rowid DESC LIMIT 1"
              ).bind(subRow.user_id).first();
              licenseKey = licRow?.key || "";

              const refRow = await env.DB.prepare(
                "SELECT ref_code FROM referrals WHERE referrer_email = ? AND status != 'expired' LIMIT 1"
              ).bind(toEmail).first();
              refCode2 = refRow?.ref_code || "";
              if (refCode2) refUrl2 = `https://cleanshothq.com/?ref=${refCode2}`;
            }

            const planName = sub.items?.data?.[0]?.price?.nickname || "CleanShot Subscriber";
            const isTrial  = (sub.trial_end ?? 0) > nowSec();
            const { html, text } = buildWelcomeEmail(userName, planName, licenseKey, refCode2, refUrl2, isTrial);
            await sendEmail(toEmail, "Welcome to CleanShot HQ — your account details inside", html, text, env);
          } catch (e) {
            console.error("welcome email error:", e.message);
          }
        })());

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

    // ── GET /download/CleanShot.exe ──────────────────────────────────────────
    // Serve signed CleanShot.exe from R2 and log the download.
    if (path === "/download/CleanShot.exe" && method === "GET") {
      if (!env.RELEASES) return err("file hosting not configured", 503);

      const obj = await env.RELEASES.get("CleanShot.exe");
      if (!obj) {
        return new Response("CleanShot.exe not yet uploaded.", {
          status: 404,
          headers: { "Content-Type": "text/plain", ...CORS },
        });
      }

      // Hash the IP for privacy — store only first 16 hex chars
      const ip = request.headers.get("CF-Connecting-IP") || "";
      const ua = (request.headers.get("User-Agent") || "").slice(0, 256);
      let ipHash = null;
      try {
        const hashBuf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ip));
        ipHash = Array.from(new Uint8Array(hashBuf))
          .map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
      } catch { /* best-effort */ }

      // Log download asynchronously — don't block the file response
      ctx.waitUntil(
        env.DB.batch([
          env.DB.prepare(
            "INSERT INTO downloads (filename, downloaded_at, ip_hash, user_agent, version) VALUES (?, ?, ?, ?, ?)"
          ).bind("CleanShot.exe", nowSec(), ipHash, ua, "3.0.12"),
          env.DB.prepare(
            `INSERT INTO download_stats (filename, total_downloads, last_downloaded)
             VALUES (?, 1, ?)
             ON CONFLICT(filename) DO UPDATE SET
               total_downloads = total_downloads + 1,
               last_downloaded = excluded.last_downloaded`
          ).bind("CleanShot.exe", nowSec()),
        ]).catch(e => console.error("download log error:", e.message))
      );

      return new Response(obj.body, {
        headers: {
          "Content-Type":        "application/octet-stream",
          "Content-Disposition": 'attachment; filename="CleanShot.exe"',
          "Cache-Control":       "public, max-age=3600",
          ...CORS,
        },
      });
    }

    // ── POST /v1/account/login ───────────────────────────────────────────────
    // Dashboard login: email + license key → signed JWT (30-day expiry).
    if (path === "/v1/account/login" && method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body?.email || !body?.license_key) {
        return err("email and license_key required");
      }

      const user = await env.DB.prepare(
        `SELECT l.key, l.type, l.expires_at, l.active,
                u.id, u.email, u.name, u.role
         FROM licenses l
         JOIN users u ON l.user_id = u.id
         WHERE l.key = ? AND LOWER(u.email) = LOWER(?)`
      ).bind(body.license_key.trim(), body.email.trim()).first();

      if (!user) return err("invalid email or license key", 401);
      if (!user.active) return err("license revoked", 403);

      if (!env.JWT_SECRET) return err("JWT not configured", 503);

      const payload = {
        sub:   user.id,
        email: user.email,
        name:  user.name,
        role:  user.role,
        iat:   nowSec(),
        exp:   nowSec() + 30 * 86400,
      };
      const token = await signJWT(payload, env.JWT_SECRET);

      // Fetch account details for the response
      const sub = await env.DB.prepare(
        "SELECT status, stripe_customer_id, current_period_end FROM subscriptions WHERE user_id = ? ORDER BY rowid DESC LIMIT 1"
      ).bind(user.id).first();

      const discount = sub?.stripe_customer_id
        ? await env.DB.prepare(
            "SELECT active_referral_count, monthly_discount_cents FROM referral_discounts WHERE referrer_stripe_id = ?"
          ).bind(sub.stripe_customer_id).first()
        : null;

      const referral = await env.DB.prepare(
        "SELECT ref_code FROM referrals WHERE referrer_email = ? AND status != 'expired' LIMIT 1"
      ).bind(user.email).first();

      const daysLeft = user.type === "trial"
        ? Math.max(0, Math.floor((user.expires_at - nowSec()) / 86400))
        : null;

      return json({
        token,
        account: {
          email:            user.email,
          name:             user.name || "",
          plan:             _planName(user.type, sub),
          status:           _accountStatus(user, sub),
          trial_ends:       user.type === "trial" ? user.expires_at : null,
          days_remaining:   daysLeft,
          next_billing:     sub?.current_period_end ?? null,
          active_referrals: discount?.active_referral_count ?? 0,
          monthly_discount: ((discount?.monthly_discount_cents ?? 0) / 100).toFixed(2),
          ref_code:         referral?.ref_code ?? null,
          referral_url:     referral?.ref_code ? `https://cleanshothq.com/?ref=${referral.ref_code}` : null,
        },
      });
    }

    // ── GET /v1/account/me ───────────────────────────────────────────────────
    // Return full account info for the authenticated dashboard user.
    if (path === "/v1/account/me" && method === "GET") {
      const jwt = await requireJWT(request, env);
      if (!jwt) return err("Authorization required", 401);

      const user = await env.DB.prepare(
        `SELECT l.key, l.type, l.expires_at, l.active,
                u.id, u.email, u.name, u.role
         FROM licenses l
         JOIN users u ON l.user_id = u.id
         WHERE u.id = ? AND l.active = 1
         ORDER BY l.rowid DESC LIMIT 1`
      ).bind(jwt.sub).first();

      if (!user) return err("account not found", 404);

      const sub = await env.DB.prepare(
        "SELECT status, stripe_customer_id, current_period_end FROM subscriptions WHERE user_id = ? ORDER BY rowid DESC LIMIT 1"
      ).bind(user.id).first();

      const discount = sub?.stripe_customer_id
        ? await env.DB.prepare(
            "SELECT active_referral_count, monthly_discount_cents FROM referral_discounts WHERE referrer_stripe_id = ?"
          ).bind(sub.stripe_customer_id).first()
        : null;

      const referral = await env.DB.prepare(
        "SELECT ref_code FROM referrals WHERE referrer_email = ? AND status != 'expired' LIMIT 1"
      ).bind(user.email).first();

      const daysLeft = user.type === "trial"
        ? Math.max(0, Math.floor((user.expires_at - nowSec()) / 86400))
        : null;

      return json({
        email:            user.email,
        name:             user.name || "",
        plan:             _planName(user.type, sub),
        status:           _accountStatus(user, sub),
        trial_ends:       user.type === "trial" ? user.expires_at : null,
        days_remaining:   daysLeft,
        next_billing:     sub?.current_period_end ?? null,
        active_referrals: discount?.active_referral_count ?? 0,
        monthly_discount: ((discount?.monthly_discount_cents ?? 0) / 100).toFixed(2),
        ref_code:         referral?.ref_code ?? null,
        referral_url:     referral?.ref_code ? `https://cleanshothq.com/?ref=${referral.ref_code}` : null,
      });
    }

    // ── GET /v1/account/stats ────────────────────────────────────────────────
    // Full savings analytics for the dashboard.
    if (path === "/v1/account/stats" && method === "GET") {
      const jwt = await requireJWT(request, env);
      if (!jwt) return err("Authorization required", 401);

      const user = await env.DB.prepare(
        "SELECT created_at FROM users WHERE id = ?"
      ).bind(jwt.sub).first();

      const accountAgeDays = user ? Math.floor((nowSec() - user.created_at) / 86400) : 0;
      const monthsActive   = Math.max(1, Math.ceil(accountAgeDays / 30));

      // Resolve license key to query hazard_log
      const licRow = await env.DB.prepare(
        "SELECT key FROM licenses WHERE user_id = ? AND active = 1 ORDER BY rowid DESC LIMIT 1"
      ).bind(jwt.sub).first();
      const licKey = licRow?.key ?? "";

      // Hazard totals grouped by type + severity
      const { results: hazardRows } = licKey
        ? await env.DB.prepare(
            `SELECT hazard_type, severity, COUNT(*) as cnt
             FROM hazard_log WHERE license_key = ?
             GROUP BY hazard_type, severity`
          ).bind(licKey).all()
        : { results: [] };

      // States covered
      const { results: stateRows } = licKey
        ? await env.DB.prepare(
            "SELECT DISTINCT state FROM hazard_log WHERE license_key = ? AND state IS NOT NULL"
          ).bind(licKey).all()
        : { results: [] };
      const statesCovered = stateRows.map(r => r.state).filter(Boolean).sort();

      const sv = calcSavings(hazardRows, monthsActive);

      return json({
        hazards: {
          total_detected: sv.totalHazards,
          by_type:        sv.byType,
          by_severity:    sv.bySeverity,
          states_covered: statesCovered,
        },
        savings: {
          data_mb_saved:      sv.dataSavedMb,
          data_cost_saved:    sv.dataCostSaved,
          fuel_gallons_saved: sv.fuelGal,
          fuel_cost_saved:    sv.fuelCostSaved,
          time_hours_saved:   sv.timeHours,
          time_value_saved:   sv.timeCostSaved,
          total_value_saved:  sv.totalValue,
          vs_competitor_cost: parseFloat((monthsActive * 12.99).toFixed(2)),
        },
        subscription: {
          months_active:          monthsActive,
          total_paid:             sv.totalPaid,
          total_value_delivered:  sv.totalValue,
          roi_multiplier:         sv.roi,
        },
      });
    }

    // ── POST /v1/account/logout ──────────────────────────────────────────────
    // Stateless JWT — logout is handled client-side by clearing localStorage.
    // This endpoint exists for future server-side session invalidation.
    if (path === "/v1/account/logout" && method === "POST") {
      return json({ ok: true });
    }

    // ── POST /v1/billing/portal ──────────────────────────────────────────────
    // Generate a Stripe Customer Portal URL for the authenticated user.
    if (path === "/v1/billing/portal" && method === "POST") {
      const jwt = await requireJWT(request, env);
      if (!jwt) return err("Authorization required", 401);

      const sub = await env.DB.prepare(
        "SELECT stripe_customer_id FROM subscriptions WHERE user_id = ? AND status = 'active' ORDER BY rowid DESC LIMIT 1"
      ).bind(jwt.sub).first();

      if (!sub?.stripe_customer_id) {
        return err("no active subscription found", 404);
      }

      const portal = await stripePost("/billing_portal/sessions", {
        customer:   sub.stripe_customer_id,
        return_url: "https://cleanshothq.com/dashboard",
      }, env);

      if (!portal.url) {
        const msg = portal.error?.message || "billing portal unavailable";
        return err(msg, 502);
      }

      return json({ url: portal.url });
    }

    // ── POST /v1/account/recover ─────────────────────────────────────────────
    // Forgot license key — look up by email and send recovery email.
    // Always returns the same message to prevent account enumeration.
    if (path === "/v1/account/recover" && method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body?.email) return err("email required");

      const email = body.email.trim().toLowerCase();
      const GENERIC = { message: "If that email is registered, you'll receive your license key shortly." };

      const allowed = await checkRateLimit(`recover:${email}`, 3, 3600, env);
      if (!allowed) return json(GENERIC); // silently rate-limit

      const user = await env.DB.prepare(
        `SELECT u.email, u.name, l.key as license_key
         FROM users u
         JOIN licenses l ON l.user_id = u.id
         WHERE LOWER(u.email) = ? AND l.active = 1
         ORDER BY l.rowid DESC LIMIT 1`
      ).bind(email).first();

      if (user) {
        ctx.waitUntil((async () => {
          const { html, text } = buildRecoveryEmail(user.name, user.license_key);
          await sendEmail(user.email, "Your CleanShot license key", html, text, env);
        })());
      }

      return json(GENERIC);
    }

    // ── POST /v1/account/resend-welcome ──────────────────────────────────────
    // Resend welcome email — verified by Stripe payment card last4.
    if (path === "/v1/account/resend-welcome" && method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body?.email || !body?.stripe_last4) return err("email and stripe_last4 required");

      const email    = body.email.trim().toLowerCase();
      const last4    = String(body.stripe_last4).replace(/\D/g, "").slice(-4);
      const GENERIC  = { message: "If we can verify your identity, you'll receive a welcome email shortly." };

      const allowed = await checkRateLimit(`resend:${email}`, 3, 3600, env);
      if (!allowed) return json(GENERIC);

      ctx.waitUntil((async () => {
        try {
          // Find Stripe customer by email
          const customers = await stripeGet(
            `/customers?email=${encodeURIComponent(email)}&limit=1`, env
          );
          const customer = customers.data?.[0];
          if (!customer) return;

          // Verify card last4
          const payMethods = await stripeGet(
            `/customers/${customer.id}/payment_methods?type=card&limit=5`, env
          );
          const matched = payMethods.data?.some(pm => pm.card?.last4 === last4);
          if (!matched) return;

          // Log security audit
          await env.DB.prepare(
            `INSERT INTO rate_limits (key, count, window_start)
             VALUES (?, 1, ?)
             ON CONFLICT(key) DO UPDATE SET count = count + 1`
          ).bind(`resend-audit:${email}`, nowSec()).run();

          // Find license key
          const subRow = await env.DB.prepare(
            "SELECT user_id FROM subscriptions WHERE stripe_customer_id = ? LIMIT 1"
          ).bind(customer.id).first();
          if (!subRow) return;

          const licRow = await env.DB.prepare(
            "SELECT key FROM licenses WHERE user_id = ? AND active = 1 ORDER BY rowid DESC LIMIT 1"
          ).bind(subRow.user_id).first();
          if (!licRow) return;

          // Get referral if any
          const refRow = await env.DB.prepare(
            "SELECT ref_code FROM referrals WHERE referrer_email = ? AND status != 'expired' LIMIT 1"
          ).bind(email).first();
          const refCode = refRow?.ref_code || "";
          const refUrl  = refCode ? `https://cleanshothq.com/?ref=${refCode}` : "";

          const { html, text } = buildWelcomeEmail(
            customer.name || "", "CleanShot Subscriber",
            licRow.key, refCode, refUrl, false
          );
          await sendEmail(email, "Welcome to CleanShot HQ — your account details inside", html, text, env);
        } catch (e) {
          console.error("resend-welcome error:", e.message);
        }
      })());

      return json(GENERIC);
    }

    // ── POST /v1/hazard/log ───────────────────────────────────────────────────
    // App reports a hazard detected and shown to a driver.
    if (path === "/v1/hazard/log" && method === "POST") {
      const licKey = getXLicenseKey(request);
      if (!licKey) return err("X-License-Key header required", 401);

      const lic = await env.DB.prepare(
        "SELECT key, active, type, expires_at FROM licenses WHERE key = ?"
      ).bind(licKey).first();
      if (!lic || !lic.active) return err("invalid or revoked license", 403);
      if (lic.type === "trial" && nowSec() > lic.expires_at) {
        return err("trial expired", 402);
      }

      const body = await request.json().catch(() => null);
      if (!body?.hazard_type || !body?.severity) {
        return err("hazard_type and severity required");
      }

      const VALID_TYPES = new Set([
        "black_ice","bridge_freeze","fog","flood","diesel_gel",
        "high_wind","mudslide","dot_incident",
      ]);
      const VALID_SEVS = new Set(["low","moderate","high","critical"]);
      if (!VALID_TYPES.has(body.hazard_type)) return err("unknown hazard_type");
      if (!VALID_SEVS.has(body.severity))     return err("unknown severity");

      await env.DB.prepare(
        `INSERT INTO hazard_log
           (license_key, hazard_type, severity, state, route, detected_at, lat, lon, acknowledged)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        licKey,
        body.hazard_type,
        body.severity,
        body.state  ? String(body.state).slice(0, 2).toUpperCase()  : null,
        body.route  ? String(body.route).slice(0, 20)               : null,
        nowSec(),
        body.lat != null ? parseFloat(body.lat) : null,
        body.lon != null ? parseFloat(body.lon) : null,
        body.acknowledged ? 1 : 0,
      ).run();

      return json({ logged: true }, 201);
    }

    // ── POST /v1/session/log ──────────────────────────────────────────────────
    // App reports a session summary when closing.
    if (path === "/v1/session/log" && method === "POST") {
      const licKey = getXLicenseKey(request);
      if (!licKey) return err("X-License-Key header required", 401);

      const lic = await env.DB.prepare(
        "SELECT key, active FROM licenses WHERE key = ?"
      ).bind(licKey).first();
      if (!lic || !lic.active) return err("invalid or revoked license", 403);

      const body = await request.json().catch(() => null);

      await env.DB.prepare(
        `INSERT INTO session_log
           (license_key, session_start, session_end, queries, hazards_detected, states_checked, miles_covered)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        licKey,
        body?.session_start ?? nowSec(),
        nowSec(),
        Math.max(0, parseInt(body?.queries          || 0, 10)),
        Math.max(0, parseInt(body?.hazards_detected || 0, 10)),
        JSON.stringify(Array.isArray(body?.states_checked) ? body.states_checked : []),
        body?.miles_covered != null ? parseFloat(body.miles_covered) : null,
      ).run();

      return json({ logged: true }, 201);
    }

    // ── GET /favicon.ico ─────────────────────────────────────────────────────
    if (path === "/favicon.ico") {
      const obj = env.RELEASES ? await env.RELEASES.get("favicon.ico") : null;
      if (!obj) return new Response(null, { status: 204 });
      return new Response(obj.body, {
        headers: {
          "Content-Type":  "image/x-icon",
          "Cache-Control": "public, max-age=86400",
        },
      });
    }

    // ── GET /flyer ────────────────────────────────────────────────────────────
    // Serve the CleanShot product flyer PDF inline in the browser.
    if (path === "/flyer") {
      if (!env.RELEASES) return err("flyer not available", 503);
      const obj = await env.RELEASES.get("CleanShotHQ_Flyer_v9.pdf");
      if (!obj) {
        return new Response("Flyer not yet uploaded.", {
          status: 404,
          headers: { "Content-Type": "text/plain", ...CORS },
        });
      }
      return new Response(obj.body, {
        headers: {
          "Content-Type":        "application/pdf",
          "Content-Disposition": 'inline; filename="CleanShotHQ_Flyer_v9.pdf"',
          "Cache-Control":       "public, max-age=3600",
          ...CORS,
        },
      });
    }

    return err("Not found", 404);
  },
};
