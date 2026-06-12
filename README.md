# TrustIQ — Continuous Identity Trust for Digital Banking

**Bank of Baroda Hackathon 2026 · Theme: Identity Trust, Protection & Safety**

> **Problem statement.** Design a *privacy-first, risk-based Identity Trust
> framework* that **continuously validates customer identities across digital
> channels**, detects high-risk events (anomalous behaviour, new-device usage,
> suspicious account-recovery attempts, account takeover), and **triggers
> real-time verification only when risk is elevated** — reducing account-takeover
> fraud while keeping good customers friction-free, staying compliant, and
> scaling across every banking channel.

TrustIQ answers it with one idea: **identity is not a gate you pass once, it is a
living trust score that moves with every action.** Instead of authenticating
*who you are* at login and trusting that forever, TrustIQ maintains a persistent
**Identity Trust Score (0–100)** for every customer and re-validates **every
login, transfer, payee-add, profile change and account-recovery attempt** in
real time against a durable **Digital Identity Passport**.

### Scope of this build
This implementation is focused squarely on **existing retail banking customers**
— the people who already have an account and use it every day across channels.
It is deliberately **not** about employee/insider monitoring or new-customer
onboarding/KYC; those are separate problems with separate owners. Keeping the
scope tight lets TrustIQ do one thing extremely well: **know the real customer
and react the instant something stops looking like them.**

---

## 1. The three core ideas

1. **Identity Trust Score** — one persistent, explainable 0–100 score per
   customer that evolves with every event. Slow to earn, fast to lose
   (asymmetric inertia): a takeover signal collapses it immediately.
2. **Digital Identity Passport** — the durable profile TrustIQ validates
   *against*: trusted devices, trusted locations, active hours, behavioural
   baseline and recovery history. It only *learns* new trusted attributes from
   low-risk events, so an attacker can't teach it.
3. **Continuous Trust Validation** — every action on every channel is re-scored
   live, producing a trust score, an identity-match score, a risk score, an
   action (allow / step-up / block) and a plain-English AI verdict.

---

## 2. How TrustIQ maps to the problem statement

| Requirement | How TrustIQ delivers it |
|-------------|-------------------------|
| **Continuously validate identity across channels** | One unified brain (`POST /api/trust/evaluate`) scores *every* event on mobile, net banking, UPI, branch, ATM and call-centre against the same persistent identity. |
| **Detect anomalous behaviour** | Behavioural biometrics (keystroke dwell/flight, swipe velocity, entropy) compared to the passport baseline lower trust. |
| **Detect new-device usage** | Device fingerprint vs the trusted-device registry; an unrecognised device drops the identity-match score. |
| **Detect impossible travel** | Geo-velocity detector flags physically impossible location jumps (Mumbai → London in minutes). |
| **Detect suspicious account recovery** | Recovery attempts re-score against the passport and can require a dynamic, deepfake-resistant liveness challenge. |
| **Detect account takeover / mule transfers** | Risk fusion + beneficiary fan-in + identity-graph fraud-ring detection surface takeovers and money-mule networks. |
| **Real-time verification only when risk is elevated** | Low risk → silent pass (zero friction). Only elevated/critical risk triggers step-up or a live **Gemini AI identity check**. |
| **Privacy-first & compliant** | PII hashed/masked before any logging or modelling, DPDP consent register, differential privacy, immutable JWT-protected audit trail. |
| **Scalable across channels & volume** | Stateless scoring API; shared state in Redis/Postgres; the same endpoint serves all channels. |

---

## 3. The decision in one paragraph

Every event is sent to the **Trust Orchestrator**, which fuses real-time ML
**risk**, the **Identity Passport match**, the evolving **Identity Trust Score**,
**beneficiary trust** (for money movement), **impossible-travel** detection and a
continuous **session trust**, then asks the **AI Fraud Analyst** for an
explainable verdict. The decision is *trust-aware*: a strongly-trusted identity
earns **less** friction on a borderline action, while a low-trust or
fraud-linked identity earns **more**.

```
 effective risk   action               what the customer feels
 ───────────────────────────────────────────────────────────────────
  0–30   safe      silent pass          nothing — it just works
 31–60   elevated  push confirmation    a soft "was this you?" on a trusted device
 61–80   high      OTP / face liveness   a mandatory step-up
 81–100  critical  block + alert         stopped, and routed to fraud ops
```

And the persistent trust band tells you *who the identity is over time*:

```
 80–100  verified       strongly trusted — consistent across devices, places, rhythm
 60–79   established    known, consistent identity with a solid history
 40–59   guarded        some inconsistency — worth watching
 20–39   untrusted      significant divergence from the real person
  0–19   compromised    likely takeover — trust has collapsed
```

---

## 4. Platform capabilities

### 4.1 Identity Trust Score Engine (`identity_trust.py`)
A single persistent 0–100 trust score per customer, stored durably so it
survives sessions and channels. It evolves from behavioural consistency, trusted
devices, location history, transaction patterns, recovery history, fraud-ring
links and session trust — with **asymmetric inertia** (rises gently, collapses
immediately on a takeover signal). Keeps a rolling history and derives a
**rising / falling / stable** trend.

### 4.2 Digital Identity Passport (`identity_passport.py`)
The durable identity profile TrustIQ validates against: trusted devices, trusted
locations, active hours, behavioural baseline and recovery history. Every event
yields an **Identity Match Score (0–100)** — "how much does this look like the
real person?" The passport only learns new trusted attributes from low-risk
events, so an attacker on a new device can't quietly become trusted.

### 4.3 Impossible Travel Detection (`impossible_travel.py`)
Remembers each identity's last authenticated location and time, then computes the
implied travel speed for the next event. A login from Mumbai then London minutes
later requires an impossible speed → a **dedicated impossible-travel alert** and a
risk boost (Haversine over a built-in city-coordinate table, with a
home-distance fallback).

### 4.4 Deepfake-Resistant Account Recovery (`liveness_challenge.py`)
Replaces static "liveness = true" with a **dynamic, randomised challenge**: a
short, unpredictable sequence of active actions (turn head, blink, read these
digits aloud) bound to a one-time nonce. It scores challenge-response correctness
+ human reaction timing + passive depth/texture into a **recovery confidence
score**. Replayed or synthetic faces fail because they can't satisfy a
never-seen sequence, are too fast, or look flat.

### 4.5 Account-Takeover & Mule Detection (`identity_graph.py` + `beneficiary_trust.py`)
A NetworkX identity graph links customers ↔ devices ↔ IPs ↔ accounts ↔ payees.
Clusters of 3+ linked identities surface as **fraud rings**; the beneficiary
engine catches **fan-in mules** (one payee receiving from many unrelated senders)
and just-added-payee large transfers. Visualised live as a **linked-accounts
map**.

### 4.6 AI Fraud Analyst (`ai_analyst.py`)
Every decision carries a plain-English, analyst-style write-up: a headline, a
narrative, the concrete contributing factors, an investigation summary, a
recommended action and a confidence value. Deterministic and rule-grounded —
every sentence traces to a numeric signal, exactly what fraud-ops and a regulator
need.

### 4.7 Multi-Channel Trust Engine (`channel_trust.py`)
One identity, many surfaces — **Mobile Banking, Internet Banking, UPI, Branch
Banking, ATM and Call Center**. Each channel keeps its own rolling trust signal,
while the persistent Identity Trust Score remains the single cross-channel source
of truth.

### 4.8 Compliance Center (`compliance.py`)
A live **DPDP 2023 + RBI** posture dashboard: PII masking, differential privacy,
a **consent register**, **explainability records**, **model versioning**,
immutable audit and data-retention controls — each with a pass/partial status.

### 4.9 Real-time AI verification — only when risk is elevated (`bank_simulator/ai_verifier.py`)
When an action would otherwise be blocked, the bank runs a **real-time identity
verification** instead of a hard wall: Google **Gemini** asks the customer a few
questions grounded in their real account and grades the answers live. Pass → the
action proceeds; fail → it's denied. This is the literal embodiment of "trigger
verification *only* when risk is elevated." A deterministic local verifier is
used automatically when no Gemini key is set.

### Supporting layers
- **`risk_engine.py`** — real-time ML risk fusion (weighted-average ⊕ noisy-OR) + identity-graph escalator.
- **`adaptive_auth.py`** — maps effective risk to silent-pass / push / OTP / block.
- **`behavioral.py`**, **`device_fingerprint.py`**, **`anomaly_detector.py`** — biometric, device and anomaly sub-scores (Isolation Forest + optional PyTorch LSTM).
- **`account_recovery.py`** — zero-trust account-recovery scoring for existing customers.
- **`privacy_layer.py`**, **`audit_logger.py`**, **`auth.py`** — PII hashing + differential privacy, append-only audit, JWT.

---

## 5. Architecture

```
        ┌─────────────────────────────────────────────────────────────┐
        │              BANK OF BARODA — CORE SIMULATOR                 │
        │   10 real customer accounts · what a normal customer sees    │
        │   sign in · transfer · add payee · change profile · recover  │
        └───────────────────────────┬─────────────────────────────────┘
                                     │ POST /api/action  (per customer action)
                                     ▼  calls TrustIQ over the X-API-Key
        ┌─────────────────────────────────────────────────────────────┐
        │   POST /api/trust/evaluate  ──►  TRUST ORCHESTRATOR           │
        │                                      │                       │
        │   ┌──────────┬───────────┬───────────┼───────────┬────────┐  │
        │   ▼          ▼           ▼           ▼           ▼        ▼  │
        │ risk_      identity_   identity_   impossible_ beneficiary ai_│
        │ engine     passport    trust       travel      trust    analyst
        │   │                                                          │
        │   ├─ behavioral · device_fingerprint · anomaly_detector       │
        │   ├─ identity_graph (fraud rings) · channel_trust             │
        │   └─ compliance · liveness_challenge · privacy · audit · JWT  │
        └───────────────┬───────────────────────────┬──────────────────┘
                        ▼                            ▼
              ┌──────────────────┐         ┌────────────────────┐
              │   FRAUD SOC UI   │         │   NEON POSTGRES     │
              │ (React command   │         │ bank_accounts ·     │
              │  center, alerts, │         │ bank_activity ·     │
              │  rings, history) │         │ bank_verify_sessions│
              └──────────────────┘         └────────────────────┘
        Redis (real-time trust/sessions/geo) + Postgres (audit) — both
        optional at runtime; in-memory fallbacks keep the demo zero-dependency.

   ML PIPELINE (offline):  synthetic_data → feature_engineering →
   train_anomaly (Isolation Forest) · train_lstm (PyTorch) · federated_sim (FedAvg)
```

The **bank simulator** is the *customer's* view — it shows only what a real BoB
customer would see (balances, actions, the occasional OTP/verification), never
the internal scores. The **SOC dashboard** is the *bank's* view, where every
trust score, risk score and verdict is visible to fraud ops.

---

## 6. Data persistence (Neon Postgres)

The bank simulator persists its state in a hosted **Neon PostgreSQL** database
across three dedicated tables (created and seeded automatically on first boot):

| Table | Holds |
|-------|-------|
| `bank_accounts` | The 10 customer accounts — balance, home city, registered device, phone, last action/verdict |
| `bank_activity` | The full action + verdict log (JSONB), newest-first, indexed by time |
| `bank_verify_sessions` | Pending real-time AI identity-verification challenges (single-use) |

Configure the DSN via `DATABASE_URL` in `bank_simulator/.env`. State now survives
restarts; use the simulator's **Reset** to restore starting balances and clear
logs.

---

## 7. How this connects to Bank of Baroda

TrustIQ is a **drop-in trust layer**, not a replacement for existing systems.

- **Every channel calls one API.** Net banking, the bob World app, UPI, branch /
  CBS, ATM and call-centre tools each POST a small JSON event to
  `/api/trust/evaluate` and receive a trust score, identity match, action and an
  explainable verdict.
- **Decision, not data.** Channels keep doing what they do; TrustIQ returns
  *pass / step-up / block* plus the reason and the identity's trust trend.
- **Step-up hand-off.** On `step_up_otp` / `block`, the channel triggers BoB's
  existing OTP / biometric / fraud-ops workflows. Recovery flows can call the
  dynamic liveness-challenge endpoints.

### Compliance & privacy fit (RBI / DPDP Act 2023)
- **Privacy-first:** PII is hashed/masked before any modelling or logging; only
  derived features are stored, never raw keystroke streams.
- **Consent register:** every processed identity has a DPDP consent record with
  purpose and expiry, viewable in the Compliance Center.
- **Explainability:** every decision carries the AI-analyst rationale and factor
  breakdown — no black boxes (RBI model-risk / FREE-AI aligned).
- **Differential privacy** noise is applied to behavioural aggregates.
- **Immutable audit trail:** every decision is appended to an INSERT-only table
  with timestamp, masked user, action, score, factors, response and model
  version. Export is JWT-protected.
- **Federated learning** (`ml/federated_sim.py`) shows models trained across
  branches **without raw customer data ever leaving a branch**.

### Scale
The scoring API is stateless (shared state lives in Redis), so it scales
horizontally behind a load balancer. Redis gives sub-50ms lookups; the identity
graph and audit log live in their own stores. The same service serves every
channel as user and transaction volumes grow.

> **Note:** This is a hackathon prototype using synthetic data and in-memory
> fallbacks. Production at BoB would wire the API to the bank's real identity
> store, device registry, CBS feed and IdP, behind the bank's security perimeter.

---

## 8. Project structure

```
trustiq/
├── backend/                      FastAPI service + the Identity Trust Platform
│   ├── main.py                   API entry point (all endpoints + WebSocket)
│   ├── trust_orchestrator.py     the unified trust brain (/api/trust/evaluate)
│   ├── identity_trust.py         persistent Identity Trust Score engine
│   ├── identity_passport.py      Digital Identity Passport + identity match
│   ├── impossible_travel.py      geo-velocity impossible-travel detection
│   ├── liveness_challenge.py     deepfake-resistant dynamic liveness (recovery)
│   ├── beneficiary_trust.py      beneficiary scoring + mule fan-in
│   ├── ai_analyst.py             explainable AI Fraud Analyst
│   ├── channel_trust.py          multi-channel trust signals
│   ├── compliance.py             DPDP + RBI Compliance Center
│   ├── risk_engine.py            real-time ML risk fusion
│   ├── adaptive_auth.py          step-up decisions
│   ├── account_recovery.py       zero-trust recovery scoring
│   ├── behavioral.py / device_fingerprint.py / anomaly_detector.py
│   ├── identity_graph.py         NetworkX fraud-ring analysis
│   ├── privacy_layer.py / audit_logger.py / auth.py / state.py / config.py
│   ├── models.py                 Pydantic contracts (trust, passport, graph, …)
│   └── Dockerfile
├── bank_simulator/               Bank of Baroda core simulator (10 accounts)
│   ├── server.py                 FastAPI app + action enforcement (port 9100)
│   ├── db.py                     Neon Postgres persistence (3 tables)
│   ├── accounts.py               the 10 seeded BoB customer accounts
│   ├── trust_client.py           calls TrustIQ over the X-API-Key integration
│   ├── ai_verifier.py            Gemini real-time identity verification
│   ├── _env.py / .env            local config (TrustIQ + DB + GEMINI_API_KEY)
│   └── index.html                single-page customer bank UI (no build step)
├── frontend/                     Fraud Command Center (React SOC console)
│   ├── index.html · styles.css · build.js · bundle.js (generated)
│   ├── app_core.jsx              API client, trust/channel helpers, Icon
│   ├── command_center.jsx        SOC home: trust widgets, channels, watchlist
│   ├── customer_profile.jsx      drill-in: passport, trust gauge, history, verdict
│   ├── fraud_ring.jsx            linked-accounts / mule-network map
│   ├── compliance_panel.jsx      DPDP + RBI dashboard
│   ├── alert_feed.jsx · risk_timeline.jsx · roster.jsx
│   ├── dashboard.jsx             shell + navigation
│   ├── mount.jsx                 renders <Dashboard/>
│   └── vendor/                   React, Recharts, Axios, Lucide (local, no CDN)
├── ml/                           Offline ML pipeline
│   ├── synthetic_data.py · feature_engineering.py
│   ├── train_anomaly.py · train_lstm.py · federated_sim.py
├── tests/                        pytest suite
├── render.yaml · README.md
```

---

## 9. Live deployment

TrustIQ runs fully in the cloud — no local servers required.

| Service | URL |
|---------|-----|
| **Bank of Baroda simulator** (customer view) | https://bob-simulator.vercel.app |
| **SOC dashboard** (bank view) | https://trust-iq-three.vercel.app |
| **TrustIQ backend API** (docs) | https://trustiq-67h0.onrender.com/docs |

| Layer | Host | Source repo |
|-------|------|-------------|
| TrustIQ backend (FastAPI + Redis) | Render | https://github.com/23110572-hash/TrustIQ |
| SOC dashboard (static React) | Vercel | https://github.com/23110572-hash/TrustIQ (`frontend/`) |
| Bank simulator (Python serverless) | Vercel | https://github.com/23110572-hash/BOB-Simulator |
| Database (shared) | Neon PostgreSQL | — |

### Environment variables to set in the hosting dashboards

**Render — TrustIQ backend**
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | the Neon Postgres DSN |
| `JWT_SECRET_KEY` | a strong secret |
| `TRUSTIQ_API_KEY` | `bob-trustiq-live-key-2026` (must match the simulator) |
| `REDIS_HOST` / `REDIS_PORT` | wired automatically from the Render Redis service |

**Vercel — BOB simulator**
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | the Neon Postgres DSN (**required** — tables auto-seed on first call) |
| `TRUSTIQ_URL` | `https://trustiq-67h0.onrender.com` |
| `TRUSTIQ_API_KEY` | `bob-trustiq-live-key-2026` |
| `GEMINI_API_KEY` | (optional) for AI identity-verification challenges |
| `GEMINI_MODEL` | (optional) defaults to `gemini-2.0-flash` |

> **Frontend note:** the dashboard loads a **precompiled `bundle.js`** plus
> **locally-vendored libraries** (`frontend/vendor/`). No in-browser
> compilation, no CDN. If you edit any `*.jsx`, rebuild with `node build.js`
> and redeploy.

---

## 10. API endpoints

### Identity Trust Platform
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/trust/evaluate` | **Unified, explainable trust decision** (any channel/event) |
| GET  | `/api/passports` | All Identity Passports (lowest trust first) |
| GET  | `/api/passport/{user_id}` | One Digital Identity Passport |
| GET  | `/api/identity/{user_id}/trust-history` | Trust score trend over time |
| GET  | `/api/graph` | Identity-graph snapshot (fraud rings) |
| GET  | `/api/channels/trust` | Per-channel trust signals |
| POST | `/api/recovery/challenge` | Issue a dynamic liveness challenge |
| POST | `/api/recovery/challenge/verify` | Score liveness → recovery confidence |
| GET  | `/api/compliance` | DPDP + RBI posture report |
| GET  | `/api/compliance/consent` | DPDP consent register |

> `POST /api/trust/evaluate` requires the integration **`X-API-Key`** header.
> The Bank of Baroda simulator is the authorised caller; the key is configured
> via `TRUSTIQ_API_KEY` in `backend/.env`.

### Core / supporting
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/event` | Score a single banking event |
| POST | `/api/recovery/evaluate` | Score an account-recovery attempt |
| GET  | `/api/alerts` | Recent alerts (optional `?category=`) |
| GET  | `/api/user/{id}/timeline` | Per-user risk timeline |
| GET  | `/api/audit/log` | Audit export **(JWT required)** |
| GET  | `/api/dashboard/stats` | Dashboard header summary |
| POST | `/api/token` | Issue a demo JWT |
| WS   | `/ws/alerts` | Live alert stream |

---

## 11. Walkthrough — drive it from the Bank simulator

Open the **Bank of Baroda simulator** at https://bob-simulator.vercel.app, pick any of the
10 customers, and act. Each action is silently scored by TrustIQ; watch the
**SOC dashboard** (https://trust-iq-three.vercel.app) react in real time. (The customer
view never shows scores — only the bank's SOC does.)

| Try this | Expected outcome |
|----------|------------------|
| Sign in from the **registered device + home city** | Trust climbs, identity match ~100%, **allowed silently** |
| Sign in from a **new device** | Identity match drops, **soft step-up** |
| Sign in from **home city**, then **London** moments later | Impossible travel → **dedicated alert, risk spikes** |
| **Transfer** from a **new device + VPN + 3 AM + erratic + new payee** | Trust collapses → would-be block → **real-time AI identity check** |
| Have **several accounts transfer to one new payee** | Fan-in mule pattern → **linked-accounts / fraud ring lights up** |
| **Recover** an account from an unrecognised device | Recovery re-scored → step-up / liveness challenge |

Then open **Accounts** to watch each identity's trust score and trend, **Linked
Accounts** for the mule map, **History** for the immutable decision log, and
**Compliance** for the live DPDP/RBI posture.

---

## 12. Testing

```bash
pytest tests -v
```
Covers the risk engine (score range, normal vs attack, weighted factors,
explanations) and the anomaly detector.

---

## 13. Tech stack

**Backend:** Python 3.11 · FastAPI · Uvicorn · scikit-learn · PyTorch · NetworkX ·
NumPy · Pandas · Redis · PostgreSQL (Neon) · psycopg2 · diffprivlib · python-jose (JWT)
**Frontend:** React 18 · Recharts · custom CSS design system · Lucide icons · Axios
**Infra:** Render (Docker) · Vercel · Neon serverless Postgres · Redis

---

*Built for the Bank of Baroda Hackathon 2026 — Identity Trust, Protection & Safety.
TrustIQ: identity isn't a gate you pass once, it's a trust you continuously earn.*
