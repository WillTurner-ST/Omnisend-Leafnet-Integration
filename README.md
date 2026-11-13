# Leafnet / NocoDB into Omnisend Retail Middleware

A robust, production-ready middleware integrating **Leafnet POS** and **NocoDB** into **Omnisend** for retail email & SMS marketing, automated post-purchase customer journeys, loyalty milestone rewards, and in-store email capture tracking.

---

## 🏗 Architecture Overview

```
                      ┌───────────────────────┐
                      │   Leafnet Retail POS  │
                      └───────┬───────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          │ (Existing Sync)                       │ (Real-Time Webhook)
          ▼                                       ▼
┌──────────────────┐                   ┌─────────────────────────┐
│      NocoDB      │                   │ Order-Completion        │
│ Leafnet Customers│                   │ Webhook                 │
│ (81 columns)     │                   └──────────┬──────────────┘
└─────────┬────────┘                              │
          │                                       │
          │ (Paging / Incremental)                │
          ▼                                       ▼
┌────────────────────────────────────────────────────────────────┐
│             Leafnet-Omnisend Python Middleware                 │
│                                                                │
│  - ContactSyncService (NocoDB -> Omnisend field mapper)        │
│  - WebhookService (Orders, Integer Cents, Real-Time Events)    │
│  - LoyaltyService (Milestones, POS Redeem, Point Ledgers)      │
│  - AttributionService (Phone-only store audits, Staff bonuses) │
│  - VerificationService (Leafnet vs NocoDB parity checker)      │
│  - SQLite Database (Deduplication, sync cursor, audit log)     │
│  - Background APScheduler (Automatic daily sync)               │
└───────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │        Omnisend         │
                   │ Contacts, Orders,       │
                   │ Events, Segments &      │
                   │ Automation Journeys     │
                   └─────────────────────────┘
```

### Core Design Principles
1. **Leafnet stays the source of truth.** Register sales, customer points, and orders originate in Leafnet.
2. **Omnisend stays the sender.** Omnisend handles campaign delivery, automation journeys, and email/SMS delivery.
3. **Two parallel data feeds:**
   - **NocoDB Contact Feed:** middleware reads customer profiles, loyalty points, and purchase recency to populate Omnisend contacts, tags, and custom properties for segment targeting.
   - **Order-Completion Webhook:** real-time webhook fires on checkout. Middleware posts the purchase in integer cents, triggers the post-purchase thank-you journey with purchased categories for product recommendations, and updates customer stats in real-time.
4. **Strict Email Validation & Phone-Only Audit:**
   - Contacts with blank or invalid emails are **never** created as blank contacts in Omnisend.
   - Phone-only customers are recorded in an in-store audit table so managers and budtenders can track email capture rates per store.

---

## 📋 Field Mappings

### NocoDB Customer Row $\rightarrow$ Omnisend Contact

| Omnisend Property | NocoDB Column | Type / Format | Behavior |
|---|---|---|---|
| `email` | `email` | Identifiers (Email) | Required for Omnisend upsert. Trimmed & lowercased. Blank skips upsert. |
| `phone` | `phone` | Identifiers (Phone) | Cleaned to E.164 (`+1...`). |
| `firstName` | `first_name` | Contact Core | Falls back to splitting `customer_name` if empty. |
| `lastName` | `last_name` | Contact Core | Falls back to remainder of `customer_name`. |
| `birthdate` | `birth_date` | Contact Core | Formatted as ISO `YYYY-MM-DD` when available. |
| `leafnet_customer_id`| `leafnet_customer_id`| Custom Property | String / Integer ID. |
| `birthday` | `birth_date` | Custom Property | Date string. |
| `home_store` | `favorite_location` | Custom Property | e.g. `red-bank`, `east-brainerd`, `lee-hwy`. |
| `signup_date` | `leafnet_created_at` | Custom Property | Date registered. Falls back to `first_visit`. |
| `last_visit_date` | `last_visit` | Custom Property | Timestamp of latest order. |
| `days_since_last_visit`| `days_since_last_visit`| Custom Property | Integer days since last store visit. |
| `visit_count` | `visit_count` | Custom Property | Integer count of store visits. |
| `order_count` | `order_count` | Custom Property | Integer count of completed orders. |
| `lifetime_value` | `lifetime_spend` | Custom Property | Float total spend (e.g. `2868.00`). |
| `average_spend` | `average_order_value`| Custom Property | Float average order value. |
| `points_balance` | `points` | Custom Property | Current loyalty points balance (e.g. `362.94`). |
| `top_category` | `favorite_category` | Custom Property | Top purchased product category (e.g. `GUMMIES`). |
| `opt_status` | `opt_status` | Custom Property | Consent status; suppresses if set to `unsubscribed`. |

### Contact Tags Applied Automatically
- `retail`, `Leafnet`
- `store:{favorite_location}` (e.g. `store:red-bank`)
- `first-time-buyer` (`order_count == 1`)
- `repeat-customer` (`order_count >= 2`)
- `vip` (`lifetime_spend >= $500.00`)
- `lapsed-45-days` (`days_since_last_visit >= 45`)
- `lapsed-90-days` (`days_since_last_visit >= 90`)
- `loyalty-tier-100` (`points >= 100`)
- `loyalty-tier-200` (`points >= 200`)

---

## 🎁 Loyalty System & Milestone Rewards

The loyalty system implements rewards mirroring the legacy Marsello tiers:
- **100 Points Milestone:** `$5 off` (Trigger code: `REWARD5OFF`)
- **200 Points Milestone:** `10% off` (Trigger code: `REWARD10PCT`)

### Workflows:
1. **Milestone Detection:** When points balance crosses a threshold, the middleware triggers an Omnisend custom event `Loyalty Milestone Reached` with the reward discount code, initiating the reward email journey.
2. **POS Checkout Redemption:** When a customer redeems points at the register, call `POST /api/loyalty/redeem` which invokes Leafnet's `loyalty_redeem` API command to deduct points in the register ledger.
3. **Balance & History Lookup:** Query live balances and itemized points transactions via `POST /api/loyalty/lookup`.

---

## 🛒 Order-Completion Webhook

When a customer completes a retail transaction:
1. Webhook payload arrives at `POST /webhooks/leafnet/order-completed`.
2. **Idempotency Check:** Order ID (e.g. `#232450`) is checked against local SQLite storage. Duplicates are cleanly skipped.
3. **Monetary Conversion:** Converts float dollar strings into **integer cents** required by Omnisend (`orderSum`, `subTotalSum`, `discountSum`, `taxSum`, and line item `price`).
4. **Omnisend Orders API:** Submits order to Omnisend (`POST /v3/orders`).
5. **Omnisend Custom Event:** Fires `Retail Purchase Completed` (`POST /v3/events`) with:
   - Order ID, total, store location
   - Category tags (for personalized product recommendations)
   - Primary category
   - Cashier attribution (`account_id`, `account_name`)
6. **Real-Time Profile Refresh:** Updates `last_visit_date`, resets `days_since_last_visit` to 0, updates `top_category`.

---

## 👥 Staff Incentives & Email Capture Auditing

- **In-Store Phone-Only Audit (`GET /api/reports/phone-only`):**
  Identifies customers with phone numbers on file who lack email addresses, grouped by retail location, allowing budtenders to prioritize email collection.
- **Staff Attribution (`POST /webhooks/leafnet/customer-updated` & `GET /api/reports/staff-email-acquisitions`):**
  Tracks which employee added an email to an existing account to support weekly bonus programs and staff incentives.

---

## 🚀 Quickstart & Setup

### 1. Requirements
- Python 3.10+
- Pip

### 2. Installation
```bash
git clone <repository_url>
cd leafnet-docs
pip install -r requirements.txt
```

### 3. Configuration
Copy the `.env.example` file to `.env` and fill in your API credentials:
```bash
cp .env.example .env
```

Key environment variables:
```ini
# Omnisend Credentials
OMNISEND_API_KEY=your_omnisend_api_key_here

# NocoDB Configuration
NOCODB_API_URL=https://app.nocodb.com
NOCODB_API_TOKEN=your_nocodb_xc_token
NOCODB_TABLE_ID=your_customers_table_id

# Leafnet API Configuration
LEAFNET_API_URL=https://snapdragon-hemp.haimenu.com/api/
LEAFNET_API_KEY=your_leafnet_api_key_here
LEAFNET_FOLDER_NAME=snapdragon-hemp

# Sync Scheduling
SYNC_INTERVAL_HOURS=24
```

---

## 💻 CLI Commands

The middleware provides a comprehensive CLI for administration and operations:

### 1. Run Customer Sync
```bash
# Incremental sync (changes since last run)
python -m middleware.cli sync

# Full sync (all records)
python -m middleware.cli sync --full
```

### 2. Verify Customer Parity (Step 9 Checklist)
Cross-checks a customer's record across Leafnet POS and NocoDB:
```bash
python -m middleware.cli verify --customer-id 20854
```

### 3. Check Loyalty Balance & Ledger
```bash
python -m middleware.cli loyalty-lookup --phone "(505) 321-4567" --history
```

### 4. Audit Phone-Only Customers
```bash
python -m middleware.cli report-phone-only
```

### 5. Start the Webhook Server
```bash
python -m middleware.cli serve --port 8000 --reload
```

---

## 📡 REST API & Webhooks Reference

Once started, explore the interactive OpenAPI documentation at `http://localhost:8000/docs`.

### Webhook Endpoints
- `POST /webhooks/leafnet/order-completed` — Receives completed retail order from Leafnet.
- `POST /webhooks/leafnet/customer-updated` — Receives customer email update events.

### Sync Endpoints
- `POST /api/sync/run?full=false` — Triggers customer sync.
- `GET /api/sync/history` — Returns recent sync run metrics.
- `GET /api/sync/cursor` — Inspects the incremental timestamp cursor.
- `POST /api/sync/cursor` — Resets or updates the cursor.

### Loyalty Endpoints
- `POST /api/loyalty/lookup` — Looks up points balance & ledger.
- `POST /api/loyalty/redeem` — Deducts points for reward redemption.
- `POST /api/loyalty/adjust` — Adjusts points manually.
- `POST /api/loyalty/create` — Creates new loyalty account.

### Reporting & Verification
- `GET /api/reports/phone-only` — Store-by-store email capture opportunity report.
- `GET /api/reports/staff-email-acquisitions` — Employee email collection leaderboard.
- `GET /api/verify/customer/{customer_id}` — Parity check between Leafnet and NocoDB.
- `GET /health` — Service readiness & status check.

---

## 🐳 Docker Deployment

Build and run from the Dockerfile:
```bash
docker build -t leafnet-omnisend-middleware .
docker run -d --name leafnet-omnisend-middleware --restart unless-stopped -p 8000:8000 --env-file .env -e DB_PATH=/app/data/middleware.db -v middleware-data:/app/data leafnet-omnisend-middleware
```
The service listens on port 8000. The SQLite database is stored in the `middleware-data` volume.

---

## 🧪 Testing

Run the test suite with `pytest`:
```bash
python -m pytest tests/ -v
```
All 12 automated test cases validate mapping rules, currency conversions, deduplication, loyalty milestones, and HTTP routes.
