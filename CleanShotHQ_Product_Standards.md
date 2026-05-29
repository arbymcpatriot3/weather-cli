# CleanShotHQ — Product Standards & Quality Philosophy
### The Standard We Set for Every Trucker on the Road

*Effective: May 2026 | CleanShotHQ LLC*

---

## Our Founding Commitment

Truck drivers operate in conditions where bad software isn't just
annoying — it's dangerous. A crash at the wrong moment, missing
road hazard data, or an app that won't load on 2G could put a
driver at risk. We take that seriously.

We will never ship software we wouldn't trust with our own safety.

---

## What We Will Never Do

### ❌ No Ads. Ever.
CleanShot and every product we build will be ad-free for life.
No banner ads, no sponsored results, no "promoted" hazard data.
When a driver sees an alert, it is because there is a real hazard —
not because someone paid us to show it.

### ❌ No Crashes Accepted
A crash is a broken promise. Every unhandled exception, every
silent failure, every blank screen is a driver who didn't get
the information they needed. We test every state, every route,
every edge case. We set the standard others measure against.

### ❌ No Slowness
Drivers on 2G, in tunnels, in low-signal mountain corridors —
they need data fast or not at all. CleanShot must respond in
under 3 seconds on any network we support. If we can't deliver
data fast, we tell the driver clearly and fall back gracefully.

### ❌ No Disappearing Features
If a feature ships, it stays. We will never remove invoices,
route history, HOS records, or any data a driver depends on
without giving them ample notice and a way to export everything
they own. Driver data belongs to the driver.

### ❌ No Bait and Switch
The price you see is the price you pay. Features listed as
included are included. If pricing changes, existing subscribers
are grandfathered or given 90 days notice minimum. The Founding
Member rate ($4.99/mo) is locked in for life — that's a promise,
not a marketing line.

### ❌ No Silence
Every support email gets a reply within 24 hours, business days.
If we can't solve a problem immediately, we acknowledge it and
give a timeline. Drivers should never feel ignored.

### ❌ No Dark Patterns
No fake countdown timers. No hidden cancellation flows. No
pre-checked upsells. Cancel anytime means cancel anytime —
one click, no phone call required.

---

## What We Always Do

### ✅ Test Every State
All 50 states have DOT/511 feeds. All 50 get tested before
every release. A trucker in Montana deserves the same quality
as a trucker in California.

### ✅ Degrade Gracefully
If road511 is down, we say so and show cached data with a
timestamp. If TTS fails, we display text. If the network drops,
we don't crash — we queue and retry silently. The app always
gives the driver something useful.

### ✅ Store Driver Data Securely
Invoices, HOS logs, route history — anything a driver generates
belongs to them. We back it up on a secure section of their
CleanShotHQ account. If they lose their phone or laptop, their
records survive. We use encryption at rest and in transit.
We never sell or share driver data.

### ✅ Earn the Subscription Every Month
A subscription is not a one-time sale. Every month we have to
justify the renewal by shipping improvements, fixing bugs, and
listening to feedback. If we stop improving, drivers should
cancel — and we'd deserve it.

### ✅ Treat Truckers as Professionals
Truckers are skilled professionals operating complex machinery
under federal regulations, managing their own business, and
keeping the country supplied. Our UI, our language, and our
support reflect that respect. No condescension, no baby steps,
no "are you sure?" for every action.

### ✅ Say What We Don't Know
If a hazard source is unavailable, we say so. If our data is
15 minutes old, we show the timestamp. We never present stale
data as live. Honesty about our limitations builds more trust
than pretending to be perfect.

---

## Data & Privacy Standards

- We collect only what we need to operate the service
- We never sell driver data to third parties — ever
- Location is used for route hazard lookups only — not stored
  unless the driver explicitly saves a route
- All account data is exportable and deletable on request
- We comply with applicable privacy laws and aim to exceed them

---

## Quality Bar for Every Release

Before any version ships:

- [ ] All 50 state DOT/511 feeds tested
- [ ] Runs clean on Windows 10 (minimum spec laptop)
- [ ] No crash on network loss, API timeout, or bad data
- [ ] TTS tested on Windows (pyttsx3) and graceful fallback on others
- [ ] Version number correct and update checker working
- [ ] No `weather-cli` or old repo references in active code
- [ ] CHANGELOG.md updated with full list of changes
- [ ] Support email tested and responding

---

## How We Handle Mistakes

We will make mistakes. When we do:

1. Acknowledge it publicly if it affected users
2. Fix it as fast as possible
3. Explain what happened and what we changed
4. If data was lost or a billing error occurred, make it right
   without asking the driver to fight for it

We don't hide bugs in release notes. We don't blame users.
We own our work.

---

## The Standard

*"Truckers deserve to have a reliable program and app.
We set the standard that they will come to love."*

— R. Bruce McCarthy, Founder, CleanShotHQ LLC

---

*This document is a living commitment. As CleanShot grows into
new products — Trucker Comms, Trucker Chow, Trucker Invoice,
and beyond — these standards travel with every one of them.*

*CleanShotHQ LLC • Salem, NJ • cleanshothq.com*
