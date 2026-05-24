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
```

---

## Step 3 — Set the admin secret

```bash
wrangler secret put ADMIN_KEY
# Enter a long random string — save it somewhere safe
# This is the key you pass as X-Admin-Key header for admin endpoints
```

---

## Step 4 — Deploy

```bash
wrangler deploy
```

Your API will be live at: `https://cleanshot-api.<your-subdomain>.workers.dev`

---

## Step 5 — Add custom domain

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

## App integration

Replace `clean-shot/core/license.py` with the new `license.py` from this folder.

Add to the top of `clean-shot/core/weather.py` main():
```python
from clean_shot.core.license import enforce_license
enforce_license(VERSION)
```
