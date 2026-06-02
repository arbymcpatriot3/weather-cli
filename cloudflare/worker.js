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

// ── Website helpers ───────────────────────────────────────────────────────────

function detectLanguage(request) {
  const url = new URL(request.url);
  const paramLang = url.searchParams.get('lang');
  if (paramLang === 'es' || paramLang === 'en') return paramLang;
  const cookie = request.headers.get('Cookie') || '';
  const cookieLang = cookie.match(/\blang=(en|es)\b/)?.[1];
  if (cookieLang) return cookieLang;
  const acceptLang = request.headers.get('Accept-Language') || '';
  if (acceptLang.toLowerCase().startsWith('es') || acceptLang.toLowerCase().includes(',es')) return 'es';
  return 'en';
}

function pageResponse(html, lang = 'en', status = 200) {
  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'public, max-age=300, stale-while-revalidate=3600',
    'Content-Language': lang,
    'Vary': 'Accept-Language',
  };
  return new Response(html, { status, headers });
}

const TRUCK_SVG = `<svg viewBox="0 0 100 60" xmlns="http://www.w3.org/2000/svg" fill="#f5a623" width="36" height="22"><rect x="2" y="18" width="58" height="30" rx="3"/><path d="M60 28 L60 48 L80 48 L80 36 L70 28 Z"/><circle cx="18" cy="52" r="7"/><circle cx="50" cy="52" r="7"/><circle cx="72" cy="52" r="7"/><rect x="4" y="10" width="28" height="9" rx="2" opacity="0.5"/></svg>`;

const SHARED_CSS = `
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow+Condensed:wght@300;400;600;700&family=Barlow:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--navy:#0d1b2a;--deep:#070e17;--orange:#f5a623;--white:#f5f0e8;--muted:#8a9bb0;--rule:rgba(245,166,35,0.25);--card:rgba(13,27,42,0.85)}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--deep);color:var(--white);font-family:'Barlow',sans-serif;line-height:1.6}
a{color:var(--orange);text-decoration:none}
a:hover{text-decoration:underline}
.nav{background:var(--navy);border-bottom:1px solid var(--rule);padding:0 2rem;display:flex;align-items:center;justify-content:space-between;height:60px;position:sticky;top:0;z-index:100}
.nav-brand{display:flex;align-items:center;gap:10px;font-family:'Bebas Neue',sans-serif;font-size:1.4rem;letter-spacing:0.05em;color:var(--white);text-decoration:none}
.nav-links{display:flex;gap:1.5rem;align-items:center;list-style:none}
.nav-links a{color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;text-decoration:none;transition:color 0.2s}
.nav-links a:hover{color:var(--orange)}
.lang-toggle{display:flex;gap:4px;align-items:center;font-family:'Barlow Condensed',sans-serif;font-size:0.85rem;font-weight:700;letter-spacing:0.06em}
.lang-toggle a{padding:3px 8px;border-radius:3px;text-decoration:none;color:var(--muted)}
.lang-toggle a.active{background:var(--orange);color:var(--deep)}
.footer{background:var(--navy);border-top:1px solid var(--rule);padding:2.5rem 2rem;text-align:center;font-family:'Barlow Condensed',sans-serif;color:var(--muted);font-size:0.9rem;line-height:2}
.footer strong{color:var(--white)}
.footer a{color:var(--muted)}
.footer .tagline{color:var(--orange);font-style:italic;margin-top:0.5rem}
.btn{display:inline-block;padding:0.75rem 2rem;border-radius:4px;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1.05rem;letter-spacing:0.08em;text-transform:uppercase;text-decoration:none;cursor:pointer;transition:all 0.2s}
.btn-primary{background:var(--orange);color:var(--deep)}
.btn-primary:hover{background:#ffc04a;text-decoration:none}
.btn-outline{background:transparent;color:var(--orange);border:2px solid var(--orange)}
.btn-outline:hover{background:rgba(245,166,35,0.1);text-decoration:none}
.container{max-width:1100px;margin:0 auto;padding:0 2rem}
.section{padding:5rem 0}
.section-title{font-family:'Bebas Neue',sans-serif;font-size:2.2rem;letter-spacing:0.08em;color:var(--orange);margin-bottom:1rem}
.section-sub{color:var(--muted);font-size:1.05rem;margin-bottom:2.5rem}
@media(max-width:700px){.nav-links{display:none}.container{padding:0 1rem}.section{padding:3rem 0}}
</style>`;

function buildNav(lang, currentPath) {
  const home    = lang === 'es' ? 'Inicio'         : 'Home';
  const promise = lang === 'es' ? 'Nuestra Promesa' : 'Our Promise';
  const sub     = lang === 'es' ? 'Suscríbete'     : 'Subscribe';
  const dl      = lang === 'es' ? 'Descargar'      : 'Download';
  const support = lang === 'es' ? 'Soporte'        : 'Support';
  const enClass = lang === 'en' ? ' class="active"' : '';
  const esClass = lang === 'es' ? ' class="active"' : '';
  const lqEn = currentPath + '?lang=en';
  const lqEs = currentPath + '?lang=es';
  return `<nav class="nav">
  <a href="/${lang === 'es' ? '?lang=es' : ''}" class="nav-brand">${TRUCK_SVG} CleanShot HQ</a>
  <ul class="nav-links">
    <li><a href="/${lang === 'es' ? '?lang=es' : ''}">${home}</a></li>
    <li><a href="/promise${lang === 'es' ? '?lang=es' : ''}">${promise}</a></li>
    <li><a href="/subscribe${lang === 'es' ? '?lang=es' : ''}">${sub}</a></li>
    <li><a href="/download${lang === 'es' ? '?lang=es' : ''}">${dl}</a></li>
    <li><a href="mailto:support@cleanshothq.com">${support}</a></li>
  </ul>
  <div class="lang-toggle">
    <a href="${lqEn}"${enClass}>EN</a>
    <a href="${lqEs}"${esClass}>ES</a>
  </div>
</nav>`;
}

function buildFooter(lang) {
  const privacy = lang === 'es' ? 'Política de Privacidad' : 'Privacy Policy';
  const terms   = lang === 'es' ? 'Términos de Servicio'   : 'Terms of Service';
  const tagline = lang === 'es'
    ? 'Construido para la carretera, no para la sala de juntas.'
    : 'Built for the road, not the boardroom.';
  return `<footer class="footer">
  <strong>CleanShotHQ LLC</strong> &middot; Salem, New Jersey &middot; cleanshothq.com<br>
  (609) 202-1087 &middot; <a href="mailto:support@cleanshothq.com">support@cleanshothq.com</a> &middot; <a href="https://x.com/CleanShotHQ">@CleanShotHQ</a><br>
  &copy; 2026 CleanShotHQ LLC &middot; <a href="/privacy">${privacy}</a> | <a href="/terms">${terms}</a>
  <div class="tagline">"${tagline}"</div>
</footer>`;
}

function metaTags(lang, path, title, desc) {
  const enDesc = 'CleanShot HQ — Real-time road intelligence for OTR truck drivers. Weather, hazard alerts, HOS advisory, smart parking. No ads, ever. Windows 10/11.';
  const canonical = `https://cleanshothq.com${path}`;
  return `
<meta name="description" content="${desc || enDesc}">
<meta name="keywords" content="truck driver app, road intelligence, OTR weather, HOS tracking, hazard alerts, trucker app, CDL app">
<meta name="author" content="CleanShotHQ LLC">
<meta property="og:title" content="${title}">
<meta property="og:description" content="${desc || enDesc}">
<meta property="og:url" content="${canonical}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@CleanShotHQ">
<meta name="twitter:title" content="${title}">
<link rel="canonical" href="${canonical}">
<link rel="alternate" hreflang="en" href="${canonical}">
<link rel="alternate" hreflang="es" href="${canonical}?lang=es">`;
}

// ── HOME PAGE ─────────────────────────────────────────────────────────────────
function homePage(lang) {
  const isEs = lang === 'es';

  const title     = isEs ? 'CleanShot HQ — Inteligencia Vial para Camioneros' : 'CleanShot HQ — Road Intelligence for OTR Drivers';
  const heroLine1 = isEs ? 'INTELIGENCIA VIAL' : 'ROAD INTELLIGENCE';
  const heroLine2 = isEs ? 'CONSTRUIDO PARA LA CARRETERA' : 'BUILT FOR THE ROAD';
  const heroSub   = isEs
    ? 'Clima en tiempo real, alertas de peligros, asesoría HOS, estacionamiento inteligente — todo en kilobytes, no megabytes. Sin anuncios. Sin tarjeta de crédito. Windows 10/11.'
    : 'Real-time weather, hazard alerts, HOS advisory, smart parking — all in kilobytes, not megabytes. No ads. No credit card required. Windows 10/11.';
  const dlBtn     = isEs ? 'Descargar Prueba Gratuita' : 'Download Free Trial';
  const subBtn    = isEs ? 'Suscríbete Ahora' : 'Subscribe Now';
  const noAds     = isEs ? 'Sin anuncios. Sin tarjeta de crédito. Windows 10/11.' : 'No ads. No credit card required. Windows 10/11.';

  const featTitle = isEs ? 'QUÉ INCLUYE' : 'WHAT\'S INCLUDED';
  const features = isEs ? [
    { icon: '🌦', title: 'Clima en Vivo', desc: 'Condiciones actuales y pronóstico para tu ruta exacta, actualizadas cada 15 minutos.' },
    { icon: '⚠️', title: 'Alertas de Peligros Viales', desc: '7 detectores activos: hielo negro, congelamiento de puentes, niebla, inundación, viento, gel de diesel, deslizamiento.' },
    { icon: '⏱', title: 'Asesoría HOS', desc: 'Reglas FMCSA 11/14/70hr monitoreadas automáticamente. Siempre al tanto de tus horas.' },
    { icon: '🌉', title: 'Alturas de Puentes', desc: 'Margen de seguridad de 1.0 ft integrado. Sin sorpresas bajo ningún puente.' },
    { icon: '🅿️', title: 'Estacionamiento Inteligente', desc: 'Sugerencias de parada conscientes de tus HOS. Sabe cuándo necesitas descansar.' },
    { icon: '⚡', title: 'Kilobytes por Consulta', desc: 'Funciona en 2G. Diseñado para zonas sin señal donde otros fallan.' },
  ] : [
    { icon: '🌦', title: 'Live Weather', desc: 'Current conditions and forecast for your exact route, updated every 15 minutes.' },
    { icon: '⚠️', title: 'Road Hazard Alerts', desc: '7 active detectors: black ice, bridge freeze, fog, flood, wind, diesel gel, mudslide.' },
    { icon: '⏱', title: 'HOS Advisory', desc: 'FMCSA 11/14/70hr rules monitored automatically. Always know your hours status.' },
    { icon: '🌉', title: 'Bridge Clearances', desc: '1.0 ft safety margin built in. No surprises under any bridge on your route.' },
    { icon: '🅿️', title: 'Smart Parking', desc: 'HOS-aware rest stop suggestions. Knows when you need to pull over before you do.' },
    { icon: '⚡', title: 'Kilobytes / Query', desc: 'Works on 2G. Engineered for dead zones where other apps fail completely.' },
  ];

  const pricingTitle = isEs ? 'PRECIOS — TODAS LAS FUNCIONES PRO INCLUIDAS' : 'PRICING — ALL PRO FEATURES INCLUDED';
  const pricingSub   = isEs ? 'Prueba gratuita de 30 días · Sin tarjeta de crédito' : '30-day free trial · No credit card required';
  const foundingNote = isEs
    ? 'Miembro Fundador: Precio bloqueado de por vida. Únete antes de que esto cambie.'
    : 'Founding Member: Lifetime locked pricing. Join before this changes.';
  const plans = isEs ? [
    { name: 'Miembro Fundador', badge: '🔒 Precio Bloqueado', mo: '$4.99/mes', yr: '—', note: 'Solo para primeros adoptadores' },
    { name: 'Operador Individual', badge: '', mo: '$7.99/mes', yr: '$69.99/año', note: '1 licencia' },
    { name: 'Flota Pequeña', badge: '', mo: '$19.99/mes', yr: '$179.99/año', note: 'Hasta 5 licencias' },
    { name: 'Flota Mediana', badge: '', mo: '$49.99/mes', yr: '$449.99/año', note: 'Hasta 15 licencias' },
  ] : [
    { name: 'Founding Member', badge: '🔒 Locked Price', mo: '$4.99/mo', yr: '—', note: 'Early adopters only' },
    { name: 'Owner-Operator', badge: '', mo: '$7.99/mo', yr: '$69.99/yr', note: '1 license' },
    { name: 'Small Fleet', badge: '', mo: '$19.99/mo', yr: '$179.99/yr', note: 'Up to 5 licenses' },
    { name: 'Mid Fleet', badge: '', mo: '$49.99/mo', yr: '$449.99/yr', note: 'Up to 15 licenses' },
  ];

  const referralNote = isEs
    ? 'Refiere a un amigo y obtén un mes gratis cuando se suscriba.'
    : 'Refer a friend and get a free month when they subscribe.';
  const subCTA = isEs ? 'Ver todos los planes →' : 'See All Plans →';

  const promiseTitle = isEs ? 'NUESTRA PROMESA' : 'OUR PROMISE';
  const promiseQuote = isEs
    ? '"Las personas que conducen este país merecen herramientas dignas de esa confianza."'
    : '"The people who drive this country deserve tools worthy of that trust."';
  const promiseCTA   = isEs ? 'Leer Nuestra Promesa Completa →' : 'Read Our Full Promise →';

  const comingTitle = isEs ? 'PRÓXIMAMENTE' : 'COMING SOON';
  const comingItems = isEs
    ? ['Reportes de Peligros Comunitarios', 'Alertas de Corredores de Alto Accidente', 'Modo Vistazo', 'Panel de Flotilla', 'App Android']
    : ['Community Hazard Reports', 'High-Accident Corridor Alerts', 'Glance Mode', 'Fleet Dashboard', 'Android App'];

  const featuresHtml = features.map(f => `
    <div style="background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:1.75rem;display:flex;flex-direction:column;gap:0.5rem">
      <div style="font-size:2rem">${f.icon}</div>
      <div style="font-family:'Bebas Neue',sans-serif;font-size:1.3rem;letter-spacing:0.06em;color:var(--orange)">${f.title}</div>
      <div style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;line-height:1.5">${f.desc}</div>
    </div>`).join('');

  const plansHtml = plans.map((p, i) => `
    <tr style="${i === 0 ? 'background:rgba(245,166,35,0.08);' : ''}">
      <td style="padding:1rem 1.25rem;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1rem;color:var(--white)">
        ${p.name}${p.badge ? `<br><span style="font-size:0.8rem;color:var(--orange);font-weight:400">${p.badge}</span>` : ''}
      </td>
      <td style="padding:1rem 1.25rem;font-family:'Barlow Condensed',sans-serif;font-size:1.05rem;color:var(--orange);font-weight:700">${p.mo}</td>
      <td style="padding:1rem 1.25rem;font-family:'Barlow Condensed',sans-serif;font-size:1.05rem;color:${p.yr === '—' ? 'var(--muted)' : 'var(--orange)'};font-weight:700">${p.yr}</td>
      <td style="padding:1rem 1.25rem;color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.9rem">${p.note}</td>
    </tr>`).join('');

  const comingHtml = comingItems.map(item =>
    `<div style="padding:0.6rem 1.4rem;background:rgba(13,27,42,0.6);border:1px solid var(--rule);border-radius:20px;font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;color:var(--muted);white-space:nowrap">${item}</div>`
  ).join('');

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
${metaTags(lang, '/', title)}
${SHARED_CSS}
<style>
.hero{min-height:88vh;display:flex;align-items:center;justify-content:center;text-align:center;position:relative;overflow:hidden;padding:4rem 2rem}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 80% 60% at 50% 40%,rgba(245,166,35,0.12) 0%,transparent 70%);animation:glow 6s ease-in-out infinite alternate}
@keyframes glow{from{opacity:0.6}to{opacity:1}}
.hero-eyebrow{font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;font-weight:700;letter-spacing:0.25em;text-transform:uppercase;color:var(--orange);margin-bottom:1rem;opacity:0.85}
.hero-h1{font-family:'Bebas Neue',sans-serif;font-size:clamp(3.5rem,10vw,7rem);letter-spacing:0.04em;line-height:0.95;color:var(--white);margin-bottom:1.5rem}
.hero-h1 span{color:var(--orange)}
.hero-sub{font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;color:var(--muted);max-width:640px;margin:0 auto 2.5rem;line-height:1.6}
.hero-ctas{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:1rem}
.hero-note{font-family:'Barlow Condensed',sans-serif;font-size:0.85rem;color:var(--muted);margin-top:0.5rem}
.features-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.25rem}
.founding-callout{background:rgba(245,166,35,0.08);border:2px solid var(--orange);border-radius:8px;padding:1.25rem 1.75rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:1rem}
.founding-callout-icon{font-size:1.8rem}
.promise-block{background:var(--card);border:1px solid var(--rule);border-left:4px solid var(--orange);border-radius:0 8px 8px 0;padding:2rem 2.5rem;max-width:760px;margin:0 auto}
.promise-quote{font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;font-weight:300;font-style:italic;color:var(--white);line-height:1.5;margin-bottom:1.25rem}
.coming-strip{display:flex;flex-wrap:wrap;gap:0.75rem;justify-content:center}
table{width:100%;border-collapse:collapse}
thead th{background:var(--navy);padding:0.75rem 1.25rem;text-align:left;font-family:'Barlow Condensed',sans-serif;font-size:0.85rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--rule)}
tbody tr{border-bottom:1px solid rgba(245,166,35,0.1)}
tbody tr:hover{background:rgba(245,166,35,0.04)}
</style>
</head>
<body>
${buildNav(lang, '/')}

<!-- HERO -->
<section class="hero">
  <div style="position:relative;z-index:1;max-width:900px;width:100%">
    <div class="hero-eyebrow">CleanShot HQ</div>
    <h1 class="hero-h1">${heroLine1}<br><span>${heroLine2}</span></h1>
    <p class="hero-sub">${heroSub}</p>
    <div class="hero-ctas">
      <a href="/download" class="btn btn-primary">${dlBtn} &darr;</a>
      <a href="/subscribe" class="btn btn-outline">${subBtn}</a>
    </div>
    <p class="hero-note">${noAds}</p>
  </div>
</section>

<!-- FEATURES -->
<section class="section" style="background:rgba(13,27,42,0.4);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)">
  <div class="container">
    <div class="section-title">${featTitle}</div>
    <div class="features-grid">${featuresHtml}</div>
  </div>
</section>

<!-- PRICING -->
<section class="section">
  <div class="container">
    <div class="section-title">${pricingTitle}</div>
    <p class="section-sub">${pricingSub}</p>
    <div class="founding-callout">
      <div class="founding-callout-icon">🔒</div>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:1rem;color:var(--white)">${foundingNote}</div>
    </div>
    <div style="overflow-x:auto;border-radius:8px;border:1px solid var(--rule);margin-bottom:1.5rem">
      <table>
        <thead>
          <tr>
            <th>${isEs ? 'Plan' : 'Plan'}</th>
            <th>${isEs ? 'Mensual' : 'Monthly'}</th>
            <th>${isEs ? 'Anual' : 'Annual'}</th>
            <th>${isEs ? 'Notas' : 'Notes'}</th>
          </tr>
        </thead>
        <tbody>${plansHtml}</tbody>
      </table>
    </div>
    <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;margin-bottom:1.5rem">${referralNote}</p>
    <a href="/subscribe" class="btn btn-primary">${subCTA}</a>
  </div>
</section>

<!-- PROMISE TEASER -->
<section class="section" style="background:rgba(13,27,42,0.4);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)">
  <div class="container">
    <div class="section-title">${promiseTitle}</div>
    <div class="promise-block">
      <div class="promise-quote">${promiseQuote}</div>
      <a href="/promise" style="font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1rem;letter-spacing:0.05em;text-transform:uppercase">${promiseCTA}</a>
    </div>
  </div>
</section>

<!-- COMING SOON -->
<section class="section">
  <div class="container">
    <div class="section-title">${comingTitle}</div>
    <div class="coming-strip">${comingHtml}</div>
  </div>
</section>

${buildFooter(lang)}
</body>
</html>`;
}

// ── PROMISE PAGE ──────────────────────────────────────────────────────────────
function promisePage(lang) {
  const isEs = lang === 'es';
  const title = isEs ? 'La Promesa de CleanShot' : 'The CleanShot Promise';

  const header       = isEs ? 'LA PROMESA DE CLEANSHOT' : 'THE CLEANSHOT PROMISE';
  const dedication   = isEs ? 'Para cada conductor que mantiene a América en movimiento —' : 'To every driver who keeps America moving —';
  const p1 = isEs
    ? 'Te vemos. No como un dato demográfico. No como una impresión a la que servir anuncios. No como un número de suscripción en una base de datos. Te vemos como el profesional que eres — hábil, experimentado, y cargando más responsabilidad cada milla de lo que la mayoría de las personas jamás entenderá. CleanShot fue construido sobre una creencia simple: las personas que conducen este país merecen herramientas dignas de esa confianza.'
    : 'We see you. Not as a demographic. Not as an impression to serve ads to. Not as a subscription number in a database. We see you as the professional you are — skilled, experienced, and carrying more responsibility every mile than most people will ever understand. CleanShot was built on a simple belief: the people who drive this country deserve tools worthy of that trust.';
  const p2 = isEs
    ? 'Eso significa que no hay anuncios abarrotando tu pantalla cuando necesitas información clara rápidamente. Sin cobros adicionales, sin patrones oscuros, sin precios de cebo. Tus datos te pertenecen — protegidos, privados, y nunca vendidos.'
    : 'That means no ads cluttering your screen when you need clear information fast. No nickel-and-diming, no dark patterns, no bait-and-switch pricing. Your data belongs to you — protected, private, and never sold.';

  const pillars = isEs ? [
    { title: 'Sin Anuncios. Nunca.', desc: 'Ningún banner, ningún patrocinio, ninguna inserción pagada. Cuando estás en la carretera a las 2am tomando una decisión crítica, la última cosa que necesitas es una pantalla llena de distracciones. Lo que ves es solo lo que importa.' },
    { title: 'Tus Datos Son Tuyos.', desc: 'Nunca vendemos, compartimos ni monetizamos tus datos de uso, datos de ubicación, ni información personal. Tu historial de rutas no es nuestro producto. Tú no eres el producto.' },
    { title: 'Precios Honestos.', desc: 'El precio que ves es el precio que pagas. Sin tarifas ocultas, sin actualizaciones forzadas, sin niveles de "acceso premium". Cada función en CleanShot está disponible para cada suscriptor al mismo nivel.' },
  ] : [
    { title: 'No Ads. Ever.', desc: 'No banners, no sponsorships, no paid insertions. When you\'re on the road at 2am making a critical decision, the last thing you need is a screen full of distractions. What you see is only what matters.' },
    { title: 'Your Data Stays Yours.', desc: 'We never sell, share, or monetize your usage data, location data, or personal information. Your route history is not our product. You are not the product.' },
    { title: 'Honest Pricing.', desc: 'The price you see is the price you pay. No hidden fees, no forced upgrades, no "premium access" tiers. Every feature in CleanShot is available to every subscriber at the same level.' },
  ];

  const p3 = isEs
    ? 'No somos una empresa tecnológica que descubrió el transporte de carga. Somos personas que respetan el transporte de carga y construimos tecnología para servirlo. La diferencia importa. Las empresas tecnológicas descubren el transporte y ven un mercado. Nosotros vemos 3.5 millones de profesionales operando equipo pesado en 4 millones de millas de carretera en cada condición climática imaginable, y preguntamos: ¿cómo hacemos eso más seguro?'
    : 'We are not a tech company that discovered trucking. We are people who respect trucking and built technology to serve it. The difference matters. Tech companies discover trucking and see a market. We see 3.5 million professionals operating heavy equipment across 4 million miles of road in every weather condition imaginable, and we ask: how do we make that safer?';

  const quote1 = isEs
    ? 'Nuestra comunidad está construida sobre la misma ética que siempre ha definido la carretera — conductores cuidando a conductores.'
    : 'Our community is built on the same ethic that has always defined the road — drivers looking out for drivers.';

  const p4 = isEs
    ? 'Construimos funciones que importan — no lo que se ve bien en un comunicado de prensa, sino lo que te mantiene más seguro en una carrera nocturna por las montañas. Lo que te advierte sobre la curva que ha metido a una docena de conductores en la zanja. Lo que te dice que la caseta de pesaje está respaldada antes de que pierdas una hora. Lo que te da un resumen completo de ruta hablado — cada peligro, cada ventana meteorológica, cada área de descanso — antes de que gires la llave.'
    : 'We build features that matter — not what looks good in a press release, but what keeps you safer on a night run through the mountains. What warns you about the curve that\'s put a dozen drivers in the ditch. What tells you the scale house is backed up before you waste an hour. What gives you a full spoken route briefing — every hazard, every weather window, every rest stop — before you ever turn the key.';

  const p5 = isEs
    ? 'Nunca dejaremos de mejorar esta herramienta. Cada función que añadimos, cada fuente de datos que integramos, cada idioma que apoyamos — todo está al servicio de un objetivo.'
    : 'We will never stop improving this tool. Every feature we add, every data source we integrate, every language we support — it is all in service of one goal.';

  const quote2 = isEs ? 'Llevarte a casa sano y salvo.' : 'Bringing you home safe.';

  const p6 = isEs
    ? 'Gracias por confiarnos esa responsabilidad. No la tomamos a la ligera.'
    : 'Thank you for trusting us with that responsibility. We don\'t take it lightly.';

  const sigName  = 'R. Bruce McCarthy, Founder';
  const sigTitle = 'CleanShot Road Intelligence';
  const sigCo    = 'CleanShotHQ LLC &middot; Salem, New Jersey';

  const pillarHtml = pillars.map(p => `
    <div style="background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:1.75rem">
      <div style="font-family:'Bebas Neue',sans-serif;font-size:1.4rem;letter-spacing:0.07em;color:var(--orange);margin-bottom:0.75rem">${p.title}</div>
      <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:1rem;line-height:1.6">${p.desc}</p>
    </div>`).join('');

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | CleanShot HQ</title>
${metaTags(lang, '/promise', title + ' | CleanShot HQ')}
${SHARED_CSS}
<style>
.promise-hero{padding:5rem 2rem 3rem;text-align:center;border-bottom:1px solid var(--rule)}
.promise-title{font-family:'Bebas Neue',sans-serif;font-size:clamp(2.5rem,7vw,5rem);letter-spacing:0.08em;color:var(--orange);margin-bottom:0.5rem}
.promise-dedication{font-family:'Barlow Condensed',sans-serif;font-style:italic;font-size:1.15rem;color:var(--muted);margin-top:0.75rem}
.prose{max-width:760px;margin:0 auto}
.prose p{font-size:1.05rem;line-height:1.8;color:rgba(245,240,232,0.85);margin-bottom:1.5rem;font-family:'Barlow',sans-serif}
.pull-quote{font-family:'Barlow Condensed',sans-serif;font-size:1.5rem;font-weight:300;font-style:italic;color:var(--white);border-left:4px solid var(--orange);padding:1rem 1.5rem;margin:2.5rem 0;line-height:1.5}
.signature{margin-top:3rem;padding-top:2rem;border-top:1px solid var(--rule)}
.signature-name{font-family:'Bebas Neue',sans-serif;font-size:1.6rem;letter-spacing:0.07em;color:var(--orange)}
.signature-title{font-family:'Barlow Condensed',sans-serif;color:var(--muted);font-size:1rem;margin-top:0.25rem;line-height:1.8}
.pillars-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.25rem;margin:2rem 0 3rem}
</style>
</head>
<body>
${buildNav(lang, '/promise')}

<section class="promise-hero">
  <div class="promise-title">${header}</div>
  <div class="promise-dedication">${dedication}</div>
</section>

<section class="section">
  <div class="container">
    <div class="prose">
      <p>${p1}</p>
      <p>${p2}</p>
    </div>

    <div class="pillars-grid">${pillarHtml}</div>

    <div class="prose">
      <p>${p3}</p>
      <div class="pull-quote">"${quote1}"</div>
      <p>${p4}</p>
      <p>${p5}</p>
      <div class="pull-quote" style="font-size:1.9rem;font-weight:600;font-style:normal;text-align:center;border:none;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:1.5rem 0">"${quote2}"</div>
      <p style="margin-top:1.5rem">${p6}</p>

      <div class="signature">
        <div class="signature-name">${sigName}</div>
        <div class="signature-title">${sigTitle}<br>${sigCo}</div>
      </div>
    </div>
  </div>
</section>

${buildFooter(lang)}
</body>
</html>`;
}

// ── DOWNLOAD PAGE ─────────────────────────────────────────────────────────────
function downloadPage(lang) {
  const isEs = lang === 'es';
  const title   = isEs ? 'Descargar CleanShot para Windows' : 'Download CleanShot for Windows';
  const version = 'v3.0.16';
  const req1 = isEs ? 'Windows 10/11 &middot; 64-bit &middot; No requiere instalación' : 'Windows 10/11 &middot; 64-bit &middot; No installation required';
  const sigNote = isEs
    ? 'Firmado por CLEANSHOTHQ LLC mediante Microsoft Azure &middot; Sin advertencias de SmartScreen'
    : 'Signed by CLEANSHOTHQ LLC via Microsoft Azure &middot; No SmartScreen warnings';
  const dlBtn = isEs ? 'Descargar CleanShot.exe' : 'Download CleanShot.exe';
  const stepsTitle = isEs ? 'CÓMO EMPEZAR' : 'HOW TO GET STARTED';
  const steps = isEs ? [
    { n: '1', title: 'Descarga el ejecutable', desc: 'Haz clic en el botón de arriba. El archivo tiene ~8MB y no requiere instalación.' },
    { n: '2', title: 'Ejecútalo directamente', desc: 'Haz doble clic en CleanShot.exe. Si ves un aviso de Windows, haz clic en "Más información" y luego "Ejecutar de todas formas". El ejecutable está firmado digitalmente.' },
    { n: '3', title: 'Regístrate para tu prueba gratuita', desc: 'Ingresa tu correo y comienza. 30 días gratis, sin tarjeta de crédito. Cuando estés listo, suscríbete desde dentro de la app.' },
  ] : [
    { n: '1', title: 'Download the executable', desc: 'Click the button above. The file is ~8MB and requires no installation.' },
    { n: '2', title: 'Run it directly', desc: 'Double-click CleanShot.exe. If you see a Windows SmartScreen prompt, click "More info" then "Run anyway." The executable is digitally signed.' },
    { n: '3', title: 'Register for your free trial', desc: 'Enter your email and go. 30 days free, no credit card. When you\'re ready, subscribe from inside the app.' },
  ];
  const androidNote = isEs
    ? 'App Android en desarrollo — ¡pronto disponible!'
    : 'Android app in development — coming soon!';
  const subNote = isEs ? '¿Listo para suscribirte?' : 'Ready to subscribe?';
  const subLink = isEs ? 'Ver planes →' : 'View plans →';

  const stepsHtml = steps.map(s => `
    <div style="display:flex;gap:1.5rem;align-items:flex-start">
      <div style="width:42px;height:42px;border-radius:50%;background:var(--orange);color:var(--deep);font-family:'Bebas Neue',sans-serif;font-size:1.4rem;display:flex;align-items:center;justify-content:center;flex-shrink:0">${s.n}</div>
      <div>
        <div style="font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1.1rem;color:var(--white);margin-bottom:0.25rem">${s.title}</div>
        <div style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;line-height:1.5">${s.desc}</div>
      </div>
    </div>`).join('');

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | CleanShot HQ</title>
${metaTags(lang, '/download', title + ' | CleanShot HQ')}
${SHARED_CSS}
<style>
.dl-hero{padding:4rem 2rem;text-align:center;border-bottom:1px solid var(--rule)}
.version-badge{display:inline-block;background:rgba(245,166,35,0.15);border:1px solid var(--orange);color:var(--orange);font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;font-weight:700;letter-spacing:0.1em;padding:0.3rem 1rem;border-radius:20px;margin-bottom:1rem}
.dl-btn-wrap{margin:2rem 0}
.dl-btn{display:inline-flex;align-items:center;gap:0.75rem;padding:1.1rem 2.5rem;background:var(--orange);color:var(--deep);border-radius:6px;font-family:'Bebas Neue',sans-serif;font-size:1.6rem;letter-spacing:0.08em;text-decoration:none;transition:all 0.2s;box-shadow:0 4px 24px rgba(245,166,35,0.3)}
.dl-btn:hover{background:#ffc04a;text-decoration:none;box-shadow:0 6px 32px rgba(245,166,35,0.45)}
.steps{display:flex;flex-direction:column;gap:1.75rem;max-width:640px;margin:0 auto}
</style>
</head>
<body>
${buildNav(lang, '/download')}

<section class="dl-hero">
  <div class="version-badge">${version}</div>
  <h1 style="font-family:'Bebas Neue',sans-serif;font-size:clamp(2rem,6vw,3.5rem);letter-spacing:0.06em;color:var(--white);margin-bottom:0.5rem">${title}</h1>
  <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:1rem;margin-bottom:0.5rem">${req1}</p>
  <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;opacity:0.7">${sigNote}</p>
  <div class="dl-btn-wrap">
    <a href="/download/CleanShot.exe" class="dl-btn">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      ${dlBtn}
    </a>
  </div>
</section>

<section class="section">
  <div class="container" style="max-width:760px">
    <div class="section-title">${stepsTitle}</div>
    <div class="steps">${stepsHtml}</div>

    <div style="margin-top:3rem;padding:1.5rem;background:rgba(13,27,42,0.6);border:1px solid var(--rule);border-radius:8px;text-align:center">
      <div style="font-size:1.5rem;margin-bottom:0.5rem">🤖</div>
      <div style="font-family:'Barlow Condensed',sans-serif;color:var(--muted);font-size:0.95rem">${androidNote}</div>
    </div>

    <div style="margin-top:2rem;text-align:center">
      <span style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:1rem">${subNote} </span>
      <a href="/subscribe" style="font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1rem">${subLink}</a>
    </div>
  </div>
</section>

${buildFooter(lang)}
</body>
</html>`;
}

// ── SUBSCRIBE PAGE ────────────────────────────────────────────────────────────
function subscribePage(lang) {
  const isEs = lang === 'es';
  const title      = isEs ? 'Suscríbete a CleanShot HQ' : 'Subscribe to CleanShot HQ';
  const header     = isEs ? 'ELIGE TU PLAN' : 'CHOOSE YOUR PLAN';
  const trialNote  = isEs ? '30 días gratis · Sin tarjeta de crédito · Cancela cuando quieras' : '30-day free trial · No credit card required · Cancel anytime';
  const foundingH  = isEs ? '🔒 MIEMBRO FUNDADOR — PRECIO BLOQUEADO DE POR VIDA' : '🔒 FOUNDING MEMBER — LIFETIME LOCKED PRICE';
  const foundingP  = isEs
    ? 'Estos primeros adoptadores recibirán $4.99/mes permanentemente — sin importar futuros aumentos de precio. Este nivel se cerrará una vez que alcancemos nuestra base de suscriptores inicial.'
    : 'These early adopters lock in $4.99/month permanently — regardless of future price increases. This tier will close once we reach our initial subscriber base.';

  // Price IDs from the VALID_PRICES set at top of file
  const plans = [
    {
      id: 'founding',
      name: isEs ? 'Miembro Fundador' : 'Founding Member',
      mo: '$4.99',
      yr: null,
      note: isEs ? 'Precio bloqueado de por vida · 1 licencia' : 'Lifetime locked price · 1 license',
      founding: true,
      priceIdMo: 'price_1Tag20LvqVzoe5iIHptcxad8',
    },
    {
      id: 'oo',
      name: isEs ? 'Operador Individual' : 'Owner-Operator',
      mo: '$7.99',
      yr: '$69.99',
      note: isEs ? '1 licencia' : '1 license',
      founding: false,
      priceIdMo: 'price_1TafmGLvqVzoe5iIoXWUIlwc',
      priceIdYr: 'price_1Tag0ZLvqVzoe5iIvp3SBZtc',
    },
    {
      id: 'sf',
      name: isEs ? 'Flota Pequeña' : 'Small Fleet',
      mo: '$19.99',
      yr: '$179.99',
      note: isEs ? 'Hasta 5 licencias' : 'Up to 5 licenses',
      founding: false,
      priceIdMo: 'price_1TafsPLvqVzoe5iIGfygkAww',
      priceIdYr: 'price_1TafujLvqVzoe5iIVYwD6eUq',
    },
    {
      id: 'mf',
      name: isEs ? 'Flota Mediana' : 'Mid Fleet',
      mo: '$49.99',
      yr: '$449.99',
      note: isEs ? 'Hasta 15 licencias' : 'Up to 15 licenses',
      founding: false,
      priceIdMo: 'price_1TafyzLvqVzoe5iITfG5kBsb',
      priceIdYr: 'price_1Tag0ZLvqVzoe5iIvp3SBZtc',
    },
  ];

  const moLabel    = isEs ? 'Mensual' : 'Monthly';
  const yrLabel    = isEs ? 'Anual (2 meses gratis)' : 'Annual (2 months free)';
  const subBtnTxt  = isEs ? 'Comenzar Prueba Gratuita' : 'Start Free Trial';
  const emailLabel = isEs ? 'Tu correo electrónico' : 'Your email address';
  const emailPh    = isEs ? 'conductor@ejemplo.com' : 'driver@example.com';
  const refLabel   = isEs ? 'Código de referido (opcional)' : 'Referral code (optional)';
  const refPh      = isEs ? 'CS-XXXX-XXXX-XXXX-XXXX' : 'CS-XXXX-XXXX-XXXX-XXXX';
  const referralNote = isEs
    ? 'Refiere a un amigo: obtén 1 mes gratis cuando se suscriba.'
    : 'Refer a friend — get 1 free month when they subscribe.';
  const afterNote  = isEs
    ? 'Después de suscribirte, descarga CleanShot y usa tu correo para activar tu licencia.'
    : 'After subscribing, download CleanShot and use your email to activate your license.';
  const dlAfter    = isEs ? 'Descargar CleanShot →' : 'Download CleanShot →';

  const plansHtml = plans.map(p => {
    const borderStyle = p.founding ? 'border:2px solid var(--orange)' : 'border:1px solid var(--rule)';
    const billingOpts = p.yr
      ? `<div style="display:flex;gap:0.5rem;margin-bottom:1rem">
          <label style="display:flex;align-items:center;gap:0.4rem;cursor:pointer;font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;color:var(--muted)">
            <input type="radio" name="billing_${p.id}" value="${p.priceIdMo}" checked> ${moLabel} ${p.mo}/mo
          </label>
          <label style="display:flex;align-items:center;gap:0.4rem;cursor:pointer;font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;color:var(--orange)">
            <input type="radio" name="billing_${p.id}" value="${p.priceIdYr}"> ${yrLabel} ${p.yr}/yr
          </label>
        </div>`
      : `<input type="hidden" name="billing_${p.id}" value="${p.priceIdMo}">`;

    return `
    <div style="background:var(--card);${borderStyle};border-radius:8px;padding:1.75rem;position:relative">
      ${p.founding ? '<div style="position:absolute;top:-12px;left:1.5rem;background:var(--orange);color:var(--deep);font-family:\'Barlow Condensed\',sans-serif;font-weight:700;font-size:0.75rem;letter-spacing:0.1em;padding:2px 10px;border-radius:10px;text-transform:uppercase">Best Value</div>' : ''}
      <div style="font-family:\'Bebas Neue\',sans-serif;font-size:1.5rem;letter-spacing:0.06em;color:var(--white);margin-bottom:0.25rem">${p.name}</div>
      <div style="font-family:\'Barlow Condensed\',sans-serif;font-size:2rem;font-weight:700;color:var(--orange);margin-bottom:0.25rem">${p.mo}<span style="font-size:1rem;color:var(--muted)">/mo</span></div>
      <div style="color:var(--muted);font-family:\'Barlow Condensed\',sans-serif;font-size:0.9rem;margin-bottom:1rem">${p.note}</div>
      ${billingOpts}
      <button type="button" onclick="startCheckout('${p.id}')" class="btn btn-primary" style="width:100%;border:none;font-size:1rem;padding:0.7rem">${subBtnTxt}</button>
    </div>`;
  }).join('');

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | CleanShot HQ</title>
${metaTags(lang, '/subscribe', title + ' | CleanShot HQ')}
${SHARED_CSS}
<style>
.sub-hero{padding:3.5rem 2rem 2rem;text-align:center;border-bottom:1px solid var(--rule)}
.plans-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1.25rem;margin-bottom:2rem}
.form-group{margin-bottom:1rem}
.form-group label{display:block;font-family:'Barlow Condensed',sans-serif;font-size:0.85rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:var(--muted);margin-bottom:0.35rem}
.form-group input[type=text],.form-group input[type=email]{width:100%;padding:0.65rem 0.9rem;background:rgba(13,27,42,0.7);border:1px solid var(--rule);border-radius:4px;color:var(--white);font-family:'Barlow Condensed',sans-serif;font-size:1rem}
.form-group input:focus{outline:none;border-color:var(--orange)}
#checkout-status{margin-top:1rem;padding:0.75rem 1rem;border-radius:4px;font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;display:none}
</style>
</head>
<body>
${buildNav(lang, '/subscribe')}

<section class="sub-hero">
  <h1 style="font-family:'Bebas Neue',sans-serif;font-size:clamp(2rem,6vw,3.5rem);letter-spacing:0.06em;color:var(--orange);margin-bottom:0.5rem">${header}</h1>
  <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:1.05rem">${trialNote}</p>
</section>

<section class="section">
  <div class="container">
    <!-- Founding Member callout -->
    <div style="background:rgba(245,166,35,0.08);border:2px solid var(--orange);border-radius:8px;padding:1.25rem 1.75rem;margin-bottom:2rem">
      <div style="font-family:'Bebas Neue',sans-serif;font-size:1.2rem;letter-spacing:0.08em;color:var(--orange);margin-bottom:0.5rem">${foundingH}</div>
      <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;line-height:1.5">${foundingP}</p>
    </div>

    <!-- Email input shared -->
    <div style="max-width:480px;margin-bottom:2rem">
      <div class="form-group">
        <label for="sub-email">${emailLabel}</label>
        <input type="email" id="sub-email" placeholder="${emailPh}">
      </div>
      <div class="form-group">
        <label for="sub-ref">${refLabel}</label>
        <input type="text" id="sub-ref" placeholder="${refPh}">
      </div>
    </div>

    <!-- Plans -->
    <div class="plans-grid">${plansHtml}</div>

    <div id="checkout-status"></div>

    <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;margin-top:1rem">${referralNote}</p>
    <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;margin-top:0.5rem">${afterNote}</p>
    <a href="/download" style="font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:0.95rem">${dlAfter}</a>
  </div>
</section>

${buildFooter(lang)}

<script>
function getSelectedPriceId(planId) {
  const radios = document.querySelectorAll('input[name="billing_' + planId + '"]');
  for (const r of radios) { if (r.checked || r.type === 'hidden') return r.value; }
  return null;
}

async function startCheckout(planId) {
  const email = document.getElementById('sub-email').value.trim();
  const ref   = document.getElementById('sub-ref').value.trim();
  const status = document.getElementById('checkout-status');

  if (!email || !email.includes('@')) {
    status.style.display = 'block';
    status.style.background = 'rgba(220,50,50,0.15)';
    status.style.border = '1px solid rgba(220,50,50,0.4)';
    status.style.color = '#ff6b6b';
    status.textContent = '${isEs ? 'Por favor ingresa un correo válido.' : 'Please enter a valid email address.'}';
    return;
  }

  const priceId = getSelectedPriceId(planId);
  if (!priceId) return;

  status.style.display = 'block';
  status.style.background = 'rgba(245,166,35,0.1)';
  status.style.border = '1px solid var(--rule)';
  status.style.color = 'var(--orange)';
  status.textContent = '${isEs ? 'Redirigiendo a Stripe...' : 'Redirecting to Stripe...'}';

  try {
    const body = { email, price_id: priceId };
    if (ref) body.referral_code = ref;
    const res = await fetch('/v1/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.url) {
      window.location.href = data.url;
    } else {
      throw new Error(data.error || 'Unknown error');
    }
  } catch (e) {
    status.style.background = 'rgba(220,50,50,0.15)';
    status.style.border = '1px solid rgba(220,50,50,0.4)';
    status.style.color = '#ff6b6b';
    status.textContent = '${isEs ? 'Error: ' : 'Error: '}' + e.message;
  }
}
</script>
</body>
</html>`;
}

// ── PRIVACY PAGE ──────────────────────────────────────────────────────────────
function privacyPage(lang) {
  const isEs = lang === 'es';
  const title = isEs ? 'Política de Privacidad' : 'Privacy Policy';

  const sections = isEs ? [
    {
      h: 'Qué recopilamos',
      body: `<p>Cuando te registras para una prueba o suscripción, recopilamos tu dirección de correo electrónico y un identificador anónimo de dispositivo (una cadena con hash — nunca datos de hardware sin procesar). Cuando descargas CleanShot, registramos la descarga con un hash de IP truncado (los primeros 16 caracteres del hash SHA-256 de tu IP) y tu cadena de agente de usuario.</p>
<p>La app envía consultas de condiciones de ruta a nuestra API. Estas consultas incluyen coordenadas de ubicación o identificadores de tramo de carretera. Registramos qué endpoints se llaman y cuándo, vinculados a tu clave de licencia (no a tu identidad personal). Los registros de sesión incluyen recuentos de sesión y conteos de peligros detectados, sin rastreo de ruta.</p>`,
    },
    {
      h: 'Cómo usamos tus datos',
      body: `<p>Usamos tu correo electrónico para: enviar tu clave de licencia, notificaciones de facturación de Stripe, y responder a solicitudes de soporte. Nunca usamos tu correo para marketing de terceros.</p>
<p>Los datos de uso (registros de sesión, registros de hazard) se usan exclusivamente para mejorar la detección y la confiabilidad del servicio. Ninguno de estos datos es visible para terceros.</p>`,
    },
    {
      h: 'Sin anuncios. Sin venta de datos.',
      body: `<p>CleanShotHQ LLC no vende, alquila, comparte ni monetiza datos de usuarios con terceros, anunciantes o corredores de datos. Nunca lo hemos hecho. Nunca lo haremos. Nuestro modelo de negocio es simple: pagas una suscripción, obtienes el servicio. Tus datos no son el producto.</p>`,
    },
    {
      h: 'Procesadores de terceros',
      body: `<p><strong>Stripe</strong> procesa todos los pagos. Su política de privacidad se aplica a los datos de pago que manejan. No almacenamos números de tarjeta de crédito. <strong>Cloudflare</strong> aloja nuestra infraestructura y puede registrar metadatos de solicitudes de acuerdo con su propia política de privacidad. <strong>ATRI Road511</strong> proporciona datos de condiciones de carretera; tus consultas pasan a través de nuestra API de proxy y no están vinculadas a tu identidad con ATRI.</p>`,
    },
    {
      h: 'Retención de datos',
      body: `<p>Los registros de sesión se conservan durante 12 meses y luego se eliminan. Los datos de la cuenta se conservan mientras tu cuenta esté activa y durante 60 días después del cierre de la cuenta. Puedes solicitar la eliminación de la cuenta en cualquier momento enviando un correo a <a href="mailto:support@cleanshothq.com">support@cleanshothq.com</a>.</p>`,
    },
    {
      h: 'Seguridad',
      body: `<p>Toda la comunicación entre la app y nuestra API está cifrada con TLS 1.2+. Las contraseñas no se usan — la autenticación es por clave de licencia + correo. Los JWT de la sesión del panel expiran en 30 días.</p>`,
    },
    {
      h: 'Contacto',
      body: `<p>CleanShotHQ LLC &middot; Salem, New Jersey<br>(609) 202-1087 &middot; <a href="mailto:support@cleanshothq.com">support@cleanshothq.com</a><br>Para solicitudes de privacidad, usa el asunto: "Solicitud de Privacidad"</p>`,
    },
  ] : [
    {
      h: 'What We Collect',
      body: `<p>When you register for a trial or subscription, we collect your email address and an anonymous device identifier (a hashed string — never raw hardware data). When you download CleanShot, we log the download with a truncated IP hash (first 16 characters of the SHA-256 hash of your IP) and your user agent string.</p>
<p>The app sends road condition queries to our API. These queries include location coordinates or road segment identifiers. We log which endpoints are called and when, tied to your license key (not your personal identity). Session logs include session counts and detected hazard counts — no route tracking.</p>`,
    },
    {
      h: 'How We Use Your Data',
      body: `<p>We use your email to: send your license key, Stripe billing notifications, and respond to support requests. We never use your email for third-party marketing.</p>
<p>Usage data (session logs, hazard logs) is used exclusively to improve detection accuracy and service reliability. None of this data is visible to third parties.</p>`,
    },
    {
      h: 'No Ads. No Data Selling.',
      body: `<p>CleanShotHQ LLC does not sell, rent, share, or monetize user data with third parties, advertisers, or data brokers. We never have. We never will. Our business model is simple: you pay a subscription, you get the service. Your data is not the product.</p>`,
    },
    {
      h: 'Third-Party Processors',
      body: `<p><strong>Stripe</strong> processes all payments. Their privacy policy applies to payment data they handle. We do not store credit card numbers. <strong>Cloudflare</strong> hosts our infrastructure and may log request metadata per their own privacy policy. <strong>ATRI Road511</strong> provides road condition data; your queries pass through our proxy API and are not linked to your identity with ATRI.</p>`,
    },
    {
      h: 'Data Retention',
      body: `<p>Session logs are retained for 12 months then deleted. Account data is retained while your account is active and for 60 days after account closure. You may request account deletion at any time by emailing <a href="mailto:support@cleanshothq.com">support@cleanshothq.com</a>.</p>`,
    },
    {
      h: 'Security',
      body: `<p>All communication between the app and our API is encrypted with TLS 1.2+. Passwords are not used — authentication is by license key + email. Dashboard session JWTs expire in 30 days.</p>`,
    },
    {
      h: 'Contact',
      body: `<p>CleanShotHQ LLC &middot; Salem, New Jersey<br>(609) 202-1087 &middot; <a href="mailto:support@cleanshothq.com">support@cleanshothq.com</a><br>For privacy requests, use subject line: "Privacy Request"</p>`,
    },
  ];

  const lastUpdated = isEs ? 'Última actualización: junio 2026' : 'Last updated: June 2026';

  const sectionsHtml = sections.map(s => `
    <div style="margin-bottom:2.5rem">
      <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.4rem;letter-spacing:0.07em;color:var(--orange);margin-bottom:0.75rem">${s.h}</h2>
      <div style="color:rgba(245,240,232,0.85);font-family:'Barlow',sans-serif;font-size:1rem;line-height:1.8">${s.body}</div>
    </div>`).join('');

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | CleanShot HQ</title>
${metaTags(lang, '/privacy', title + ' | CleanShot HQ')}
${SHARED_CSS}
</head>
<body>
${buildNav(lang, '/privacy')}
<section class="section">
  <div class="container" style="max-width:820px">
    <div class="section-title">${title.toUpperCase()}</div>
    <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;margin-bottom:3rem">${lastUpdated}</p>
    ${sectionsHtml}
  </div>
</section>
${buildFooter(lang)}
</body>
</html>`;
}

// ── TERMS PAGE ────────────────────────────────────────────────────────────────
function termsPage(lang) {
  const isEs = lang === 'es';
  const title = isEs ? 'Términos de Servicio' : 'Terms of Service';
  const lastUpdated = isEs ? 'Última actualización: junio 2026' : 'Last updated: June 2026';

  const sections = isEs ? [
    {
      h: 'Descripción del Servicio',
      body: `<p>CleanShotHQ LLC ("la Compañía", "nosotros") proporciona CleanShot Road Intelligence, una aplicación de escritorio para Windows y servicios API asociados diseñados para conductores de camiones OTR. El servicio incluye datos meteorológicos de ruta, detección de peligros, asesoría de horas de servicio (HOS), datos de altura de puentes e información de estacionamiento.</p>
<p>Los datos proporcionados son solo para fines informativos. El Servicio no reemplaza el juicio profesional, el conocimiento CDL o la capacitación de seguridad. Los conductores siguen siendo responsables de tomar decisiones seguras de conducción independientemente de la salida del Servicio.</p>`,
    },
    {
      h: 'Obligaciones del Usuario',
      body: `<p>Al usar CleanShot, aceptas: (1) proporcionar información de registro precisa; (2) no compartir tu clave de licencia más allá del número de licencias de tu plan; (3) no realizar ingeniería inversa, descompilar ni modificar el software; (4) no usar el Servicio para ningún propósito ilegal; (5) no intentar acceder a sistemas o datos no autorizados.</p>`,
    },
    {
      h: 'Facturación y Suscripciones',
      body: `<p>Las suscripciones se facturan mensual o anualmente según el plan que elijas. Los pagos son procesados por Stripe. Las suscripciones se renuevan automáticamente a menos que se cancelen antes de la fecha de renovación. Los reembolsos se otorgan a discreción de la Compañía dentro de los 7 días posteriores al cobro de renovación si el Servicio no estuvo disponible durante ≥48 horas continuas durante el período de facturación.</p>
<p>Los precios de Miembro Fundador están bloqueados de por vida para los suscriptores existentes. Nos reservamos el derecho de cambiar los precios para nuevas suscripciones con un aviso de 30 días.</p>`,
    },
    {
      h: 'Disponibilidad del Servicio',
      body: `<p>Nos esforzamos por ≥99% de disponibilidad mensual. El mantenimiento planificado se anuncia con al menos 24 horas de anticipación. No somos responsables por interrupciones causadas por proveedores de datos de terceros (ATRI Road511, fuentes meteorológicas) o fuerza mayor.</p>`,
    },
    {
      h: 'Limitación de Responsabilidad',
      body: `<p>EN LA MÁXIMA MEDIDA PERMITIDA POR LA LEY APLICABLE, CLEANSHOTHQ LLC NO SERÁ RESPONSABLE DE DAÑOS INDIRECTOS, INCIDENTALES, ESPECIALES, CONSECUENTES O PUNITIVOS. NUESTRA RESPONSABILIDAD TOTAL NO EXCEDERÁ EL MONTO PAGADO POR TI POR EL SERVICIO EN LOS ÚLTIMOS 12 MESES.</p>
<p>El Servicio se proporciona "tal cual" sin garantías de ningún tipo. No garantizamos la precisión de los datos meteorológicos, condiciones de carretera o cualquier otra información proporcionada.</p>`,
    },
    {
      h: 'Cancelación de Cuenta',
      body: `<p>Puedes cancelar tu suscripción en cualquier momento a través del portal de facturación o contactando a soporte. La cancelación es efectiva al final del período de facturación actual. Nos reservamos el derecho de suspender o terminar cuentas por violación de estos Términos.</p>`,
    },
    {
      h: 'Ley Aplicable',
      body: `<p>Estos Términos se rigen por las leyes del Estado de Nueva Jersey, sin tener en cuenta los principios de conflicto de leyes. Cualquier disputa estará sujeta a la jurisdicción exclusiva de los tribunales de Salem County, Nueva Jersey.</p>`,
    },
    {
      h: 'Contacto',
      body: `<p>CleanShotHQ LLC &middot; Salem, New Jersey<br>(609) 202-1087 &middot; <a href="mailto:support@cleanshothq.com">support@cleanshothq.com</a></p>`,
    },
  ] : [
    {
      h: 'Service Description',
      body: `<p>CleanShotHQ LLC ("the Company", "we", "us") provides CleanShot Road Intelligence, a Windows desktop application and associated API services designed for OTR truck drivers. The service includes route weather data, hazard detection, Hours of Service (HOS) advisory, bridge height data, and parking information.</p>
<p>Data provided is for informational purposes only. The Service does not replace professional judgment, CDL knowledge, or safety training. Drivers remain responsible for making safe driving decisions independent of Service output.</p>`,
    },
    {
      h: 'User Obligations',
      body: `<p>By using CleanShot, you agree to: (1) provide accurate registration information; (2) not share your license key beyond the number of licenses in your plan; (3) not reverse-engineer, decompile, or modify the software; (4) not use the Service for any unlawful purpose; (5) not attempt to access unauthorized systems or data.</p>`,
    },
    {
      h: 'Billing & Subscriptions',
      body: `<p>Subscriptions are billed monthly or annually depending on the plan you select. Payments are processed by Stripe. Subscriptions auto-renew unless cancelled before the renewal date. Refunds are granted at Company discretion within 7 days of a renewal charge if the Service was unavailable for ≥48 continuous hours during the billing period.</p>
<p>Founding Member pricing is lifetime-locked for existing subscribers. We reserve the right to change pricing for new subscriptions with 30 days notice.</p>`,
    },
    {
      h: 'Service Availability',
      body: `<p>We target ≥99% monthly uptime. Planned maintenance is announced at least 24 hours in advance. We are not liable for outages caused by third-party data providers (ATRI Road511, weather sources) or force majeure.</p>`,
    },
    {
      h: 'Limitation of Liability',
      body: `<p>TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, CLEANSHOTHQ LLC SHALL NOT BE LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES. OUR TOTAL LIABILITY SHALL NOT EXCEED THE AMOUNT PAID BY YOU FOR THE SERVICE IN THE PRECEDING 12 MONTHS.</p>
<p>The Service is provided "as is" without warranties of any kind. We do not guarantee the accuracy of weather data, road conditions, or any other information provided.</p>`,
    },
    {
      h: 'Account Termination',
      body: `<p>You may cancel your subscription at any time via the billing portal or by contacting support. Cancellation is effective at the end of the current billing period. We reserve the right to suspend or terminate accounts for violation of these Terms.</p>`,
    },
    {
      h: 'Governing Law',
      body: `<p>These Terms are governed by the laws of the State of New Jersey, without regard to conflict of law principles. Any disputes shall be subject to the exclusive jurisdiction of the courts of Salem County, New Jersey.</p>`,
    },
    {
      h: 'Contact',
      body: `<p>CleanShotHQ LLC &middot; Salem, New Jersey<br>(609) 202-1087 &middot; <a href="mailto:support@cleanshothq.com">support@cleanshothq.com</a></p>`,
    },
  ];

  const sectionsHtml = sections.map(s => `
    <div style="margin-bottom:2.5rem">
      <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.4rem;letter-spacing:0.07em;color:var(--orange);margin-bottom:0.75rem">${s.h}</h2>
      <div style="color:rgba(245,240,232,0.85);font-family:'Barlow',sans-serif;font-size:1rem;line-height:1.8">${s.body}</div>
    </div>`).join('');

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | CleanShot HQ</title>
${metaTags(lang, '/terms', title + ' | CleanShot HQ')}
${SHARED_CSS}
</head>
<body>
${buildNav(lang, '/terms')}
<section class="section">
  <div class="container" style="max-width:820px">
    <div class="section-title">${title.toUpperCase()}</div>
    <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;margin-bottom:3rem">${lastUpdated}</p>
    ${sectionsHtml}
  </div>
</section>
${buildFooter(lang)}
</body>
</html>`;
}

// ── VERIFY PAGE ───────────────────────────────────────────────────────────────
function verifyPage(lang) {
  const isEs = lang === 'es';
  const title      = isEs ? 'Verificar Licencia' : 'Verify License';
  const header     = isEs ? 'VERIFICAR TU LICENCIA' : 'VERIFY YOUR LICENSE';
  const sub        = isEs ? 'Ingresa tu clave de licencia y correo para confirmar el estado de tu cuenta.' : 'Enter your license key and email to confirm your account status.';
  const keyLabel   = isEs ? 'Clave de Licencia' : 'License Key';
  const keyPh      = 'CS-XXXX-XXXX-XXXX-XXXX';
  const emailLabel = isEs ? 'Correo Electrónico' : 'Email Address';
  const emailPh    = isEs ? 'tu@correo.com' : 'you@example.com';
  const btnTxt     = isEs ? 'Verificar Licencia' : 'Verify License';

  const statusLabels = isEs ? {
    checking: 'Verificando...',
    active: 'Licencia activa',
    trial: 'Prueba activa',
    expired: 'Prueba vencida — por favor suscríbete',
    invalid: 'Licencia no encontrada',
    error: 'Error al verificar — intenta de nuevo',
    mismatch: 'El correo no coincide con esta licencia',
  } : {
    checking: 'Checking...',
    active: 'License active',
    trial: 'Trial active',
    expired: 'Trial expired — please subscribe',
    invalid: 'License not found',
    error: 'Verification error — please try again',
    mismatch: 'Email does not match this license',
  };

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} | CleanShot HQ</title>
${metaTags(lang, '/verify', title + ' | CleanShot HQ')}
${SHARED_CSS}
<style>
.verify-card{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:2.5rem;max-width:520px;margin:4rem auto}
.form-group{margin-bottom:1.25rem}
.form-group label{display:block;font-family:'Barlow Condensed',sans-serif;font-size:0.85rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--muted);margin-bottom:0.35rem}
.form-group input{width:100%;padding:0.75rem 1rem;background:rgba(7,14,23,0.7);border:1px solid var(--rule);border-radius:4px;color:var(--white);font-family:'Barlow Condensed',sans-serif;font-size:1.05rem;letter-spacing:0.04em}
.form-group input:focus{outline:none;border-color:var(--orange)}
#result{margin-top:1.5rem;padding:1rem 1.25rem;border-radius:6px;font-family:'Barlow Condensed',sans-serif;font-size:1rem;display:none}
.result-ok{background:rgba(50,200,100,0.12);border:1px solid rgba(50,200,100,0.3);color:#6ee7a0}
.result-err{background:rgba(220,50,50,0.12);border:1px solid rgba(220,50,50,0.3);color:#ff8080}
.result-detail{font-size:0.9rem;color:var(--muted);margin-top:0.5rem;line-height:1.6}
</style>
</head>
<body>
${buildNav(lang, '/verify')}

<section class="section">
  <div class="container">
    <div class="verify-card">
      <div style="font-family:'Bebas Neue',sans-serif;font-size:2rem;letter-spacing:0.08em;color:var(--orange);margin-bottom:0.5rem">${header}</div>
      <p style="color:var(--muted);font-family:'Barlow Condensed',sans-serif;font-size:0.95rem;margin-bottom:1.75rem">${sub}</p>

      <div class="form-group">
        <label for="v-key">${keyLabel}</label>
        <input type="text" id="v-key" placeholder="${keyPh}" autocomplete="off" spellcheck="false">
      </div>
      <div class="form-group">
        <label for="v-email">${emailLabel}</label>
        <input type="email" id="v-email" placeholder="${emailPh}">
      </div>
      <button onclick="verifyLicense()" class="btn btn-primary" style="width:100%;border:none">${btnTxt}</button>

      <div id="result"></div>
    </div>
  </div>
</section>

${buildFooter(lang)}

<script>
async function verifyLicense() {
  const key   = document.getElementById('v-key').value.trim().toUpperCase();
  const email = document.getElementById('v-email').value.trim();
  const result = document.getElementById('result');

  result.className = '';
  result.style.display = 'block';
  result.innerHTML = '<span>${statusLabels.checking}</span>';

  if (!key || !email) {
    result.className = 'result-err';
    result.innerHTML = '<span>${isEs ? 'Ingresa tu clave y correo.' : 'Please enter your key and email.'}</span>';
    return;
  }

  try {
    const res = await fetch('/v1/license', {
      headers: { 'Authorization': 'Bearer ' + key, 'X-Email': email },
    });
    const data = await res.json();

    if (res.status === 403 && data.error && data.error.includes('blocked')) {
      result.className = 'result-err';
      result.innerHTML = '<span>${statusLabels.invalid}</span>';
      return;
    }

    if (!res.ok) {
      result.className = 'result-err';
      result.innerHTML = '<span>' + (data.error || '${statusLabels.invalid}') + '</span>';
      return;
    }

    const status = data.status || 'active';
    const exp    = data.expires_at ? new Date(data.expires_at * 1000).toLocaleDateString() : null;
    const type   = data.type || '';
    const isOk   = ['active', 'trial', 'subscribed'].includes(status);

    result.className = isOk ? 'result-ok' : 'result-err';
    const statusText = isOk
      ? (status === 'trial' ? '${statusLabels.trial}' : '${statusLabels.active}')
      : '${statusLabels.expired}';
    result.innerHTML = '<strong>' + statusText + '</strong>' +
      (exp ? '<div class="result-detail">${isEs ? 'Válido hasta' : 'Valid through'}: ' + exp + '</div>' : '') +
      (type ? '<div class="result-detail">${isEs ? 'Tipo' : 'Type'}: ' + type + '</div>' : '');
  } catch (e) {
    result.className = 'result-err';
    result.innerHTML = '<span>${statusLabels.error}</span>';
  }
}

document.getElementById('v-key').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') verifyLicense();
});
document.getElementById('v-email').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') verifyLicense();
});
</script>
</body>
</html>`;
}

// ── SITEMAP + ROBOTS ──────────────────────────────────────────────────────────
function serveSitemap() {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url><loc>https://cleanshothq.com/</loc><changefreq>weekly</changefreq><priority>1.0</priority>
    <xhtml:link rel="alternate" hreflang="en" href="https://cleanshothq.com/"/>
    <xhtml:link rel="alternate" hreflang="es" href="https://cleanshothq.com/?lang=es"/>
  </url>
  <url><loc>https://cleanshothq.com/promise</loc><priority>0.9</priority></url>
  <url><loc>https://cleanshothq.com/subscribe</loc><priority>0.9</priority></url>
  <url><loc>https://cleanshothq.com/download</loc><priority>0.8</priority></url>
  <url><loc>https://cleanshothq.com/privacy</loc><priority>0.5</priority></url>
  <url><loc>https://cleanshothq.com/terms</loc><priority>0.5</priority></url>
</urlset>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/xml', 'Cache-Control': 'public, max-age=3600' } });
}

function serveRobots() {
  const txt = `User-agent: *\nAllow: /\nDisallow: /dashboard\nDisallow: /verify\nSitemap: https://cleanshothq.com/sitemap.xml`;
  return new Response(txt, { headers: { 'Content-Type': 'text/plain', 'Cache-Control': 'public, max-age=3600' } });
}

// ── Security event logger ─────────────────────────────────────────────────────
async function logSecurityEvent(userId, eventType, severity, deviceId, deviceFingerprint, details, env) {
  try {
    await env.DB.prepare(
      `INSERT INTO security_events (id, user_id, event_type, severity, device_id, device_fingerprint, details, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      crypto.randomUUID(), userId || null, eventType, severity,
      deviceId || null, deviceFingerprint || null,
      details ? JSON.stringify(details) : null,
      Math.floor(Date.now() / 1000)
    ).run();
  } catch { /* never let logging break the request */ }
}

// ── OTP generation + verification ────────────────────────────────────────────
function maskEmail(email) {
  const [user, domain] = email.split('@');
  return (user || '').slice(0, 2) + '***@' + (domain || '');
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function generateOTP(userId, email, purpose, ipAddress, env) {
  const now = Math.floor(Date.now() / 1000);
  const recentCount = await env.DB.prepare(
    `SELECT COUNT(*) as c FROM otp_codes WHERE user_id = ? AND created_at > ? AND purpose = ?`
  ).bind(userId, now - 600, purpose).first();
  if (recentCount.c >= 3) {
    return { status: 'rate_limited', message: 'Too many codes requested. Please wait 10 minutes.' };
  }
  const encoder = new TextEncoder();
  const secret = env.OTP_HMAC_SECRET || 'fallback-not-secure';
  const data = `${userId}:${now}:${Math.random()}`;
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(data));
  const bytes = new Uint8Array(sig);
  const code = String(((bytes[0] << 16) | (bytes[1] << 8) | bytes[2]) % 1000000).padStart(6, '0');
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO otp_codes (id, user_id, email, code, purpose, used, attempts, expires_at, created_at, ip_address)
     VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)`
  ).bind(id, userId, email, code, purpose, now + 600, now, ipAddress || null).run();
  await logSecurityEvent(userId, 'otp_sent', 'info', null, null, { purpose, email: maskEmail(email) }, env);
  return { status: 'sent', otpId: id, expiresAt: now + 600, code };
}

async function verifyOTP(userId, code, purpose, env) {
  const now = Math.floor(Date.now() / 1000);
  const otp = await env.DB.prepare(
    `SELECT * FROM otp_codes WHERE user_id = ? AND purpose = ? AND used = 0 AND expires_at > ?
     ORDER BY created_at DESC LIMIT 1`
  ).bind(userId, purpose, now).first();
  if (!otp) {
    await logSecurityEvent(userId, 'otp_expired', 'info', null, null, { purpose }, env);
    return { status: 'not_found', message: 'No active verification code. Please request a new one.' };
  }
  if (otp.attempts >= 5) {
    await logSecurityEvent(userId, 'otp_locked', 'warning', null, null, { purpose, attempts: otp.attempts }, env);
    return { status: 'locked', message: 'Too many incorrect attempts. Please request a new code.' };
  }
  await env.DB.prepare('UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?').bind(otp.id).run();
  if (!timingSafeEqual(String(code), String(otp.code))) {
    await logSecurityEvent(userId, 'otp_failed', 'warning', null, null, { purpose, attempt: otp.attempts + 1 }, env);
    const remaining = 5 - (otp.attempts + 1);
    return { status: 'invalid', message: `Incorrect code. ${remaining} attempt${remaining !== 1 ? 's' : ''} remaining.` };
  }
  await env.DB.prepare('UPDATE otp_codes SET used = 1 WHERE id = ?').bind(otp.id).run();
  await logSecurityEvent(userId, 'otp_verified', 'info', null, null, { purpose }, env);
  return { status: 'verified' };
}

// ── OTP email via Resend ──────────────────────────────────────────────────────
function buildOTPEmailHTML(code, purpose) {
  const purposeText = {
    new_device: 'verify a new device on your account',
    login: 'sign in to your account',
    password_reset: 'reset your password'
  }[purpose] || 'verify your identity';
  return `<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a1520;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a1520;padding:40px 20px;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#0d1b2a;border:1px solid rgba(245,166,35,0.25);max-width:560px;width:100%;">
<tr><td style="padding:28px 36px 20px;border-bottom:3px solid #f5a623;">
  <h1 style="margin:0;font-size:28px;letter-spacing:4px;color:#f5f0e8;font-weight:900;text-transform:uppercase;">CLEAN<span style="color:#f5a623;">SHOT</span></h1>
  <p style="margin:4px 0 0;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#7a8fa6;">Security Verification</p>
</td></tr>
<tr><td style="padding:32px 36px;">
  <p style="font-size:15px;color:#f5f0e8;margin:0 0 12px;font-weight:600;">Your verification code</p>
  <p style="font-size:14px;color:#b8c8d8;margin:0 0 28px;line-height:1.6;">Someone is trying to ${purposeText}. If this was you, enter the code below.</p>
  <div style="text-align:center;margin:0 0 28px;">
    <div style="display:inline-block;background:#0a1520;border:2px solid #f5a623;padding:18px 40px;">
      <span style="font-size:2.4rem;font-weight:900;letter-spacing:0.3em;color:#f5a623;font-family:monospace;">${code}</span>
    </div>
    <p style="font-size:12px;color:#7a8fa6;margin:10px 0 0;">Expires in <strong style="color:#f5f0e8;">10 minutes</strong> &middot; One use only</p>
  </div>
  <hr style="border:none;border-top:1px solid rgba(245,166,35,0.15);margin:0 0 20px;">
  <p style="font-size:12px;color:#4a5a6a;margin:0;line-height:1.6;">Not you? Contact <a href="mailto:support@cleanshothq.com" style="color:#f5a623;">support@cleanshothq.com</a></p>
</td></tr>
<tr><td style="padding:16px 36px;border-top:1px solid rgba(245,166,35,0.12);">
  <p style="font-size:11px;color:#4a5a6a;margin:0;">&copy; 2026 CleanShotHQ LLC &middot; Salem, New Jersey</p>
</td></tr>
</table>
</td></tr></table></body></html>`;
}

async function sendOTPEmail(email, code, purpose, env) {
  try {
    await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: 'CleanShot Security <security@cleanshothq.com>',
        to: email,
        subject: 'CleanShot — Your verification code',
        html: buildOTPEmailHTML(code, purpose),
      }),
    });
  } catch(e) { console.error('sendOTPEmail error:', e.message); }
}

async function sendSecurityAlertEmail(userId, alertType, details, env) {
  try {
    const user = await env.DB.prepare('SELECT email FROM users WHERE id = ?').bind(userId).first();
    if (!user) return;
    const subjects = {
      impossible_travel: 'CleanShot Security Alert — Unusual Login Detected',
      device_limit_exceeded: 'CleanShot — Device Limit Reached',
    };
    const bodies = {
      impossible_travel: `We detected a login to your CleanShot account from ${details.location || 'an unexpected location'}, approximately ${details.distance || '?'} miles from your last known location. If this was not you, contact support immediately.`,
      device_limit_exceeded: `Someone tried to add a new device to your account but your plan limit has been reached. If this was not you, contact support immediately.`,
    };
    const subject = subjects[alertType] || 'CleanShot Security Alert';
    const bodyText = bodies[alertType] || 'Unusual activity was detected on your account.';
    const html = `<!DOCTYPE html><html><body style="background:#0a1520;color:#f5f0e8;font-family:Arial,sans-serif;padding:40px;">
<h2 style="color:#f5a623;">Security Alert</h2><p>${bodyText}</p>
<p><a href="mailto:support@cleanshothq.com" style="color:#f5a623;">Contact Support</a></p>
<p style="font-size:11px;color:#4a5a6a;">CleanShotHQ LLC &middot; Salem, New Jersey</p></body></html>`;
    await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: 'CleanShot Security <security@cleanshothq.com>', to: user.email, subject, html }),
    });
  } catch(e) { console.error('sendSecurityAlertEmail error:', e.message); }
}

// ── Session management ────────────────────────────────────────────────────────
async function createSession(userId, deviceId, request, env) {
  const now = Math.floor(Date.now() / 1000);
  const cf = request.cf || {};
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  const token = Array.from(array).map(b => b.toString(16).padStart(2, '0')).join('');
  await env.DB.prepare(
    `INSERT INTO sessions (token, user_id, device_id, ip_address, geo_country, geo_region, geo_lat, geo_lon, user_agent, created_at, last_seen, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    token, userId, deviceId || null,
    request.headers.get('CF-Connecting-IP'),
    cf.country || null, cf.region || null,
    parseFloat(cf.latitude) || null, parseFloat(cf.longitude) || null,
    (request.headers.get('User-Agent') || '').slice(0, 200),
    now, now, now + 86400
  ).run();
  return token;
}

async function validateSession(token, env) {
  const now = Math.floor(Date.now() / 1000);
  if (!token || token.length !== 64) return null;
  const session = await env.DB.prepare(
    `SELECT s.*, u.email, u.tier, u.status, u.device_limit
     FROM sessions s JOIN users u ON s.user_id = u.id
     WHERE s.token = ? AND s.expires_at > ?`
  ).bind(token, now).first();
  if (!session) return null;
  if (session.status === 'banned' || session.status === 'suspended') return null;
  await env.DB.prepare('UPDATE sessions SET last_seen = ? WHERE token = ?').bind(now, token).run();
  return session;
}

async function revokeSession(token, env) {
  await env.DB.prepare('DELETE FROM sessions WHERE token = ?').bind(token).run();
}

async function revokeAllUserSessions(userId, env) {
  await env.DB.prepare('DELETE FROM sessions WHERE user_id = ?').bind(userId).run();
}

// ── Device management ─────────────────────────────────────────────────────────
function sanitizeDeviceName(name) {
  if (!name) return 'Unknown Device';
  return name.replace(/[^a-zA-Z0-9\s\-]/g, '').slice(0, 50).trim() || 'Unknown Device';
}

async function registerOrRecognizeDevice(userId, fingerprint, platform, deviceName, env) {
  const now = Math.floor(Date.now() / 1000);
  const blacklisted = await env.DB.prepare(
    'SELECT fingerprint FROM device_blacklist WHERE fingerprint = ?'
  ).bind(fingerprint).first();
  if (blacklisted) {
    await logSecurityEvent(userId, 'login_blocked', 'critical', null, fingerprint, { reason: 'blacklisted_device' }, env);
    return { status: 'blacklisted', message: 'This device has been blocked.' };
  }
  const existing = await env.DB.prepare(
    'SELECT * FROM devices WHERE user_id = ? AND device_fingerprint = ?'
  ).bind(userId, fingerprint).first();
  if (existing) {
    await env.DB.prepare('UPDATE devices SET last_seen = ? WHERE id = ?').bind(now, existing.id).run();
    return { status: 'recognized', deviceId: existing.id, trusted: existing.trusted === 1 };
  }
  const user = await env.DB.prepare('SELECT device_limit FROM users WHERE id = ?').bind(userId).first();
  const deviceCount = await env.DB.prepare(
    'SELECT COUNT(*) as count FROM devices WHERE user_id = ?'
  ).bind(userId).first();
  if (deviceCount.count >= (user?.device_limit ?? 2)) {
    await logSecurityEvent(userId, 'device_limit_exceeded', 'warning', null, fingerprint,
      { limit: user?.device_limit, current: deviceCount.count }, env);
    return { status: 'limit_exceeded',
      message: `Device limit reached (${user?.device_limit ?? 2}). Please deauthorize a device at cleanshothq.com/account.`,
      current_devices: deviceCount.count, limit: user?.device_limit ?? 2 };
  }
  return { status: 'new_device', fingerprint, platform: platform || 'windows', deviceName: sanitizeDeviceName(deviceName) };
}

async function completeDeviceRegistration(userId, fingerprint, platform, deviceName, env) {
  const now = Math.floor(Date.now() / 1000);
  const deviceId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO devices (id, user_id, device_fingerprint, device_name, platform, trusted, registered_at, last_seen)
     VALUES (?, ?, ?, ?, ?, 1, ?, ?)`
  ).bind(deviceId, userId, fingerprint, sanitizeDeviceName(deviceName), platform || 'windows', now, now).run();
  await logSecurityEvent(userId, 'device_registered', 'info', deviceId, fingerprint, { platform, deviceName }, env);
  return deviceId;
}

// ── Geo-anomaly detection ─────────────────────────────────────────────────────
function haversineDistanceMiles(lat1, lon1, lat2, lon2) {
  const R = 3959;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
    Math.cos(lat1 * Math.PI/180) * Math.cos(lat2 * Math.PI/180) * Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

async function checkGeoAnomaly(userId, request, env) {
  const cf = request.cf || {};
  const currentLat = parseFloat(cf.latitude) || null;
  const currentLon = parseFloat(cf.longitude) || null;
  if (!currentLat || !currentLon) return { anomaly: false };
  const now = Math.floor(Date.now() / 1000);
  const recent = await env.DB.prepare(
    `SELECT * FROM sessions WHERE user_id = ? AND geo_lat IS NOT NULL AND last_seen > ?
     ORDER BY last_seen DESC LIMIT 1`
  ).bind(userId, now - 3600).first();
  if (!recent) return { anomaly: false, lat: currentLat, lon: currentLon };
  const distance = haversineDistanceMiles(recent.geo_lat, recent.geo_lon, currentLat, currentLon);
  const hoursElapsed = (now - recent.last_seen) / 3600;
  const impliedSpeed = hoursElapsed > 0 ? distance / hoursElapsed : Infinity;
  const country = cf.country || null;
  const region  = cf.region  || null;
  if (impliedSpeed > 600 && distance > 200) {
    await logSecurityEvent(userId, 'login_impossible', 'critical', null, null, {
      distance_miles: Math.round(distance),
      hours_elapsed: Math.round(hoursElapsed * 10) / 10,
      implied_speed_mph: Math.round(impliedSpeed),
      prev_location: `${recent.geo_country}/${recent.geo_region}`,
      new_location: `${country}/${region}`,
    }, env);
    await env.DB.prepare("UPDATE users SET status = 'flagged' WHERE id = ? AND status = 'active'").bind(userId).run();
    await sendSecurityAlertEmail(userId, 'impossible_travel', { location: `${country}/${region}`, distance: Math.round(distance) }, env);
    return { anomaly: true, type: 'impossible_travel', severity: 'critical' };
  }
  if (distance > 100 && hoursElapsed < 1) {
    await logSecurityEvent(userId, 'login_suspicious', 'warning', null, null, {
      distance_miles: Math.round(distance), hours_elapsed: Math.round(hoursElapsed * 60) + ' min',
      prev_location: `${recent.geo_country}/${recent.geo_region}`, new_location: `${country}/${region}`
    }, env);
    return { anomaly: true, type: 'suspicious', severity: 'warning' };
  }
  return { anomaly: false, lat: currentLat, lon: currentLon, country, region };
}

// ── Auth route handlers ────────────────────────────────────────────────────────

async function handleLogin(request, env) {
  const body = await request.json().catch(() => null);
  if (!body?.email || !body?.device_fingerprint) return err('email and device_fingerprint required');
  const email = body.email.trim().toLowerCase();
  const user = await env.DB.prepare('SELECT * FROM users WHERE LOWER(email) = ?').bind(email).first();
  if (!user) return err('Account not found', 404);
  if (user.status === 'banned') return err('This account has been suspended. Contact support@cleanshothq.com.', 403);
  if (user.status === 'cancelled') return json({
    success: false, code: 'subscription_cancelled',
    message: 'Your subscription has expired. Please renew at cleanshothq.com/subscribe.',
    renew_url: 'https://cleanshothq.com/subscribe'
  }, 402);
  const deviceResult = await registerOrRecognizeDevice(
    user.id, body.device_fingerprint, body.device_platform, body.device_name, env
  );
  if (deviceResult.status === 'blacklisted') return err(deviceResult.message, 403);
  if (deviceResult.status === 'limit_exceeded') {
    await sendSecurityAlertEmail(user.id, 'device_limit_exceeded', {}, env);
    return json({ success: false, code: 'device_limit_exceeded', ...deviceResult }, 403);
  }
  if (deviceResult.status === 'new_device') {
    const otpResult = await generateOTP(user.id, user.email, 'new_device', request.headers.get('CF-Connecting-IP'), env);
    if (otpResult.status === 'rate_limited') return err(otpResult.message, 429);
    await sendOTPEmail(user.email, otpResult.code, 'new_device', env);
    await logSecurityEvent(user.id, 'login_new_device', 'info', null, body.device_fingerprint, {}, env);
    return json({ success: false, requires_otp: true, otp_sent: true,
      message: `A verification code has been sent to ${maskEmail(user.email)}. Enter it to authorize this device.`,
      masked_email: maskEmail(user.email) });
  }
  const geo = await checkGeoAnomaly(user.id, request, env);
  if (geo.anomaly && geo.type === 'impossible_travel') {
    const otpResult = await generateOTP(user.id, user.email, 'login', request.headers.get('CF-Connecting-IP'), env);
    if (otpResult.status !== 'rate_limited') await sendOTPEmail(user.email, otpResult.code, 'login', env);
    return json({ success: false, requires_otp: true, otp_sent: true,
      message: `Unusual login location detected. A verification code has been sent to ${maskEmail(user.email)}.`,
      masked_email: maskEmail(user.email) });
  }
  const sessionToken = await createSession(user.id, deviceResult.deviceId, request, env);
  await logSecurityEvent(user.id, 'login_success', 'info', deviceResult.deviceId, body.device_fingerprint, {}, env);
  return json({ success: true, session_token: sessionToken,
    expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { email: user.email, tier: user.tier, status: user.status, device_limit: user.device_limit }
  });
}

async function handleVerifyOTP(request, env) {
  const body = await request.json().catch(() => null);
  if (!body?.email || !body?.code || !body?.device_fingerprint) {
    return err('email, code, and device_fingerprint required');
  }
  const email = body.email.trim().toLowerCase();
  const user = await env.DB.prepare('SELECT * FROM users WHERE LOWER(email) = ?').bind(email).first();
  if (!user) return err('Account not found', 404);
  const result = await verifyOTP(user.id, String(body.code).trim(), 'new_device', env);
  if (result.status === 'not_found') {
    const loginResult = await verifyOTP(user.id, String(body.code).trim(), 'login', env);
    if (loginResult.status !== 'verified') return json({ success: false, ...loginResult }, 400);
    const sessionToken = await createSession(user.id, null, request, env);
    return json({ success: true, session_token: sessionToken, expires_at: Math.floor(Date.now()/1000) + 86400,
      device_registered: false, message: 'Verification successful.' });
  }
  if (result.status !== 'verified') return json({ success: false, ...result }, 400);
  const deviceId = await completeDeviceRegistration(user.id, body.device_fingerprint,
    body.device_platform, body.device_name, env);
  const sessionToken = await createSession(user.id, deviceId, request, env);
  return json({ success: true, session_token: sessionToken, expires_at: Math.floor(Date.now()/1000) + 86400,
    device_registered: true, message: 'Device verified and registered successfully.' });
}

async function handleResendOTP(request, env) {
  const body = await request.json().catch(() => null);
  if (!body?.email) return err('email required');
  const email = body.email.trim().toLowerCase();
  const user = await env.DB.prepare('SELECT * FROM users WHERE LOWER(email) = ?').bind(email).first();
  if (!user) return json({ success: true, message: 'If that email is registered, a code was sent.' });
  const purpose = body.purpose || 'new_device';
  const otpResult = await generateOTP(user.id, user.email, purpose, request.headers.get('CF-Connecting-IP'), env);
  if (otpResult.status === 'rate_limited') return err(otpResult.message, 429);
  await sendOTPEmail(user.email, otpResult.code, purpose, env);
  return json({ success: true, masked_email: maskEmail(user.email), message: `Code sent to ${maskEmail(user.email)}.` });
}

async function handleValidate(request, env) {
  const token = (request.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '').trim();
  const session = await validateSession(token, env);
  if (!session) return json({ valid: false, reason: 'expired' }, 401);
  const fp = request.headers.get('X-Device-Fingerprint');
  if (fp && session.device_id) {
    const device = await env.DB.prepare('SELECT device_fingerprint FROM devices WHERE id = ?').bind(session.device_id).first();
    if (device && device.device_fingerprint !== fp) {
      await logSecurityEvent(session.user_id, 'login_suspicious', 'warning', session.device_id, fp,
        { reason: 'fingerprint_mismatch' }, env);
    }
  }
  return json({ valid: true, user: { email: session.email, tier: session.tier,
    status: session.status, device_limit: session.device_limit }, expires_at: session.expires_at });
}

async function handleLogout(request, env) {
  const token = (request.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '').trim();
  if (token) await revokeSession(token, env);
  return json({ success: true });
}

async function handleListDevices(request, env) {
  const token = (request.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '').trim();
  const session = await validateSession(token, env);
  if (!session) return err('Authorization required', 401);
  const devices = await env.DB.prepare(
    'SELECT id, device_name, platform, trusted, registered_at, last_seen FROM devices WHERE user_id = ? ORDER BY last_seen DESC'
  ).bind(session.user_id).all();
  const user = await env.DB.prepare('SELECT device_limit FROM users WHERE id = ?').bind(session.user_id).first();
  return json({ devices: devices.results || [], count: (devices.results || []).length, limit: user?.device_limit ?? 2 });
}

async function handleDeauthorizeDevice(request, env, path) {
  const token = (request.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '').trim();
  const session = await validateSession(token, env);
  if (!session) return err('Authorization required', 401);
  const deviceId = path.replace('/v1/account/devices/', '');
  const device = await env.DB.prepare('SELECT * FROM devices WHERE id = ? AND user_id = ?').bind(deviceId, session.user_id).first();
  if (!device) return err('Device not found', 404);
  await env.DB.prepare('DELETE FROM devices WHERE id = ?').bind(deviceId).run();
  await env.DB.prepare('DELETE FROM sessions WHERE device_id = ?').bind(deviceId).run();
  await logSecurityEvent(session.user_id, 'device_deauthorized', 'info', deviceId, device.device_fingerprint, {}, env);
  return json({ success: true, message: 'Device deauthorized successfully.' });
}

async function handleAdminSecurity(request, env, path) {
  if (!isAdminAuthorized(request, env)) return err('Unauthorized', 401);
  const body = await request.json().catch(() => ({}));
  if (path === '/v1/admin/security/events') {
    const url = new URL(request.url);
    const type     = url.searchParams.get('type') || null;
    const severity = url.searchParams.get('severity') || null;
    const limit    = Math.min(parseInt(url.searchParams.get('limit') || '50'), 200);
    const offset   = parseInt(url.searchParams.get('offset') || '0');
    let q = 'SELECT * FROM security_events WHERE 1=1';
    const binds = [];
    if (type)     { q += ' AND event_type = ?'; binds.push(type); }
    if (severity) { q += ' AND severity = ?';   binds.push(severity); }
    q += ' ORDER BY created_at DESC LIMIT ? OFFSET ?';
    binds.push(limit, offset);
    const rows = await env.DB.prepare(q).bind(...binds).all();
    return json({ events: rows.results || [], count: (rows.results || []).length });
  }
  if (path === '/v1/admin/security/flagged-accounts') {
    const rows = await env.DB.prepare(
      `SELECT u.id, u.email, u.status, u.created_at,
              se.event_type, se.created_at as last_event_at, se.details
       FROM users u
       LEFT JOIN security_events se ON se.user_id = u.id AND se.id = (
         SELECT id FROM security_events WHERE user_id = u.id ORDER BY created_at DESC LIMIT 1)
       WHERE u.status = 'flagged' ORDER BY u.created_at DESC`
    ).all();
    return json({ accounts: rows.results || [] });
  }
  if (path === '/v1/admin/security/ban-device' && request.method === 'POST') {
    if (!body?.fingerprint || !body?.reason) return err('fingerprint and reason required');
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      `INSERT INTO device_blacklist (fingerprint, reason, banned_by, banned_at, notes) VALUES (?, ?, 'admin', ?, ?)
       ON CONFLICT(fingerprint) DO UPDATE SET reason=excluded.reason, banned_at=excluded.banned_at, notes=excluded.notes`
    ).bind(body.fingerprint, body.reason, now, body.notes || null).run();
    await env.DB.prepare(
      `DELETE FROM sessions WHERE device_id IN (SELECT id FROM devices WHERE device_fingerprint = ?)`
    ).bind(body.fingerprint).run();
    await logSecurityEvent(null, 'device_blacklisted', 'critical', null, body.fingerprint, { reason: body.reason }, env);
    return json({ success: true, message: 'Device blacklisted and sessions revoked.' });
  }
  if (path === '/v1/admin/security/ban-account' && request.method === 'POST') {
    if (!body?.userId) return err('userId required');
    await env.DB.prepare("UPDATE users SET status = 'banned' WHERE id = ?").bind(body.userId).run();
    await revokeAllUserSessions(body.userId, env);
    await logSecurityEvent(body.userId, 'account_suspended', 'critical', null, null, { reason: body.reason }, env);
    return json({ success: true, message: 'Account banned and all sessions revoked.' });
  }
  if (path === '/v1/admin/security/clear-flag' && request.method === 'POST') {
    if (!body?.userId) return err('userId required');
    await env.DB.prepare("UPDATE users SET status = 'active' WHERE id = ? AND status = 'flagged'").bind(body.userId).run();
    return json({ success: true, message: 'Flag cleared.' });
  }
  return err('Unknown admin security endpoint', 404);
}

// ── Scheduled cleanup ─────────────────────────────────────────────────────────
async function purgeExpired(env) {
  const now = Math.floor(Date.now() / 1000);
  const cutoff = now - 86400;
  await env.DB.prepare('DELETE FROM sessions WHERE expires_at < ?').bind(now).run();
  await env.DB.prepare('DELETE FROM otp_codes WHERE created_at < ? OR (used = 1 AND created_at < ?)').bind(cutoff, now).run();
}

// ── Route handler ─────────────────────────────────────────────────────────────
export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(purgeExpired(env));
  },

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
          ).bind("CleanShot.exe", nowSec(), ipHash, ua, "3.0.16"),
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

    // ── Auth endpoints ────────────────────────────────────────────────────────
    if (path === '/v1/auth/login'      && method === 'POST') return handleLogin(request, env);
    if (path === '/v1/auth/verify-otp' && method === 'POST') return handleVerifyOTP(request, env);
    if (path === '/v1/auth/resend-otp' && method === 'POST') return handleResendOTP(request, env);
    if (path === '/v1/auth/logout'     && method === 'POST') return handleLogout(request, env);
    if (path === '/v1/auth/validate'   && method === 'GET')  return handleValidate(request, env);
    if (path === '/v1/account/devices' && method === 'GET')  return handleListDevices(request, env);
    if (path.startsWith('/v1/account/devices/') && method === 'DELETE') return handleDeauthorizeDevice(request, env, path);
    if (path.startsWith('/v1/admin/security/')) return handleAdminSecurity(request, env, path);

    // ── Website pages ────────────────────────────────────────────────────────
    const lang = detectLanguage(request);

    if (path === '/set-lang' && method === 'POST') {
      const body = await request.json().catch(() => ({}));
      const newLang = body.lang === 'es' ? 'es' : 'en';
      const referer = request.headers.get('Referer') || '/';
      return new Response(null, {
        status: 302,
        headers: {
          Location: referer,
          'Set-Cookie': `lang=${newLang}; Max-Age=31536000; Path=/; SameSite=Lax`,
        },
      });
    }

    if (path === '/' || path === '') return pageResponse(homePage(lang), lang);
    if (path === '/promise')  return pageResponse(promisePage(lang), lang);
    if (path === '/download' && !url.pathname.endsWith('.exe')) return pageResponse(downloadPage(lang), lang);
    if (path === '/subscribe') return pageResponse(subscribePage(lang), lang);
    if (path === '/privacy')  return pageResponse(privacyPage(lang), lang);
    if (path === '/terms')    return pageResponse(termsPage(lang), lang);
    if (path === '/verify')   return pageResponse(verifyPage(lang), lang);
    if (path === '/sitemap.xml') return serveSitemap();
    if (path === '/robots.txt')  return serveRobots();

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
          "Content-Disposition": 'inline; filename="CleanShotHQ_Flyer.pdf"',
          "Cache-Control":       "public, max-age=86400",
          ...CORS,
        },
      });
    }

    return err("Not found", 404);
  },
};
