# CleanShot Cloudflare Backend — Deployment Guide

## Prerequisites
- Cloudflare account with cleanshothq.com added
- Node.js installed
- `npm install -g wrangler` then `wrangler login`

---

## Step 1 — Create the D1 database

```bash
wrangler d1 create cleanshot-db
```

Copy the `database_id` from the output and paste it into `wrangler.toml`.

---

## Step 2 — Run the schema

```bash
wrangler d1 execute cleanshot-db --file=schema.sql
wrangler d1 execute cleanshot-db --file=migrations/001_referrals.sql
```

---

## Step 3 — Set secrets

```bash
wrangler secret put ADMIN_KEY
# Enter a long random string — save it somewhere safe
# This is the key you pass as X-Admin-Key header for admin endpoints

wrangler secret put STRIPE_SECRET_KEY
# Enter your Stripe secret key: sk_live_... (or sk_test_... for testing)

wrangler secret put STRIPE_WEBHOOK_SECRET
# Enter the webhook signing secret from Step 5 below: whsec_...

wrangler secret put R511_API_KEY
# Enter your road511.com API key: r511_...
```

---

## Step 4 — Deploy

```bash
wrangler deploy
```

Your API will be live at: `https://cleanshot-api.<your-subdomain>.workers.dev`

---

## Step 5 — Configure Stripe webhook

In the [Stripe Dashboard](https://dashboard.stripe.com) → Developers → Webhooks → Add endpoint:

- **Endpoint URL:** `https://api.cleanshothq.com/v1/webhooks/stripe`
- **Events to listen for:**
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`

After saving, click **Reveal** next to "Signing secret" and copy the `whsec_...` value.
Then set it: `wrangler secret put STRIPE_WEBHOOK_SECRET`

---

## Step 7 — Add custom domain

In Cloudflare Dashboard → Workers & Pages → cleanshot-api → Settings → Triggers:
- Add route: `api.cleanshothq.com/*`

Then update `API_BASE` in `license.py` to `https://api.cleanshothq.com/v1`

---

## Admin API usage

All admin endpoints require the header: `X-Admin-Key: <your secret>`

### List all users
```bash
curl https://api.cleanshothq.com/v1/admin/users \
  -H "X-Admin-Key: YOUR_SECRET"
```

### Extend a tester's trial (e.g. 60 more days)
```bash
curl -X POST https://api.cleanshothq.com/v1/extend \
  -H "X-Admin-Key: YOUR_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"license_key": "CS-XXXX-XXXX-XXXX-XXXX", "days": 60}'
```

### Block a device
```bash
curl -X POST https://api.cleanshothq.com/v1/admin/block \
  -H "X-Admin-Key: YOUR_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"machine_id": "abc123..."}'
```

---

## Referral & checkout API usage

### Start a checkout session (with optional referral)
```bash
curl -X POST https://api.cleanshothq.com/v1/checkout \
  -H "Content-Type: application/json" \
  -d '{
    "price_id":   "price_1Tag20LvqVzoe5iIHptcxad8",
    "ref_code":   "bruce-4x7k",
    "success_url": "https://cleanshothq.com/success",
    "cancel_url":  "https://cleanshothq.com/#pricing"
  }'
# Returns: { "checkout_url": "https://checkout.stripe.com/..." }
```

### Generate a referral code (subscriber only)
```bash
curl -X POST https://api.cleanshothq.com/v1/referral/generate \
  -H "Authorization: Bearer CS-XXXX-XXXX-XXXX-XXXX"
# Returns: { "ref_code": "bruce-4x7k", "referral_url": "https://cleanshothq.com/?ref=bruce-4x7k" }
```

### Check referral stats
```bash
curl https://api.cleanshothq.com/v1/referral/status \
  -H "Authorization: Bearer CS-XXXX-XXXX-XXXX-XXXX"
# Returns: active_referrals, monthly_discount, ref_code, referral_url
```

---

## App integration

Replace `clean-shot/core/license.py` with the new `license.py` from this folder.

Add to the top of `clean-shot/core/weather.py` main():
```python
from clean_shot.core.license import enforce_license
enforce_license(VERSION)
```
