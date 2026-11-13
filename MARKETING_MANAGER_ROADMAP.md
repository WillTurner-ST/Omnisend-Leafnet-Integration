# Retail Email & Loyalty Rollout: Marketing Manager Playbook & Roadmap

This document is the step-by-step, reproducible roadmap for rolling out **Leafnet Retail POS + NocoDB $\rightarrow$ Omnisend**. It covers **where we are today**, **what remains to go live**, and **exact copy-paste recipes** for building every segment, automation journey, and loyalty reward in Omnisend.

---

## 1. Where We Are Today (Status Snapshot)

| Component | Status | Details |
|---|---|---|
| **NocoDB Customer Sync Feed** | **READY** | Leafnet customer profiles, spend, visits, and points are syncing into NocoDB (`Leafnet Customers` table). |
| **Omnisend Middleware Service** | **BUILT & TESTED** | Python FastAPI middleware ([`middleware/`](./middleware)) is complete with 14/14 passing automated tests. |
| **Category Normalizer & Recommendations** | **BUILT & TESTED** | Granular POS categories automatically map to clean buckets (`gummies`, `beverages`, `flower`, `pre-rolls`, `vapes`, `concentrates`, `edibles`, `accessories`) + cross-sell recommendations. |
| **Marsello-Style Loyalty Milestones** | **BUILT & TESTED** | 100 pts ($\$$5 off), 200 pts (10% off), 300 pts ($\$$15 off), 500 pts (25% off) triggers + live points-to-next-reward calculation. |
| **Phone-Only Store Audit & Staff Attribution** | **BUILT & TESTED** | Tracks phone-only accounts by store and credits employees when existing phone-only customers add an email or sign up at checkout. |
| **Live Connection & Deployment** | **NEXT STEP** | Needs `.env` API keys populated, container hosted on a public URL, and Leafnet order webhook pointed to our URL. |
| **Leafnet Vendor Ask (Existing Account Edits)** | **OPEN VENDOR ASK** | We infer staff attribution from sales + sync transitions today; Leafnet still needs to log `employee_id` when a cashier edits an email without a sale. |

---

## 2. What Else We Need To Do Before Launch (Pre-Flight Checklist)

### A. For Tech / DevOps (Takes ~45 Minutes)
1. **Populate `.env` Credentials:**
   - `OMNISEND_API_KEY`: Generate in **Omnisend $\rightarrow$ Store Settings $\rightarrow$ API Keys**.
   - `NOCODB_API_URL`, `NOCODB_API_TOKEN`, `NOCODB_TABLE_ID`: From the NocoDB `Leafnet Customers` table.
   - `LEAFNET_API_KEY`, `LEAFNET_FOLDER_NAME`: Confirmed (`snapdragon-hemp`).
2. **Deploy Middleware Container:**
   - Deploy from the Dockerfile on Coolify (or Railway / Render / Fly.io) with HTTPS enabled (e.g. `https://retail-sync.yourdomain.com`).
3. **Run Verification & Initial Sync:**
   - Run `python -m middleware.cli verify --customer-id 20854` on 5–10 known customers to verify NocoDB $\leftrightarrow$ Leafnet parity.
   - Run `python -m middleware.cli sync --full` to push the initial retail customer base into Omnisend.
4. **Point Leafnet Order-Completion Webhook:**
   - Set Leafnet's order webhook URL to:
     `POST https://retail-sync.yourdomain.com/webhooks/leafnet/order-completed`
5. **Send 1 Test Event per Custom Trigger:**
   - Omnisend only displays custom events in the Automation Trigger dropdown *after* each event has fired at least once. Firing one test order and one test sync registers:
     - `Retail Purchase Completed`
     - `New Loyalty Signup`
     - `Loyalty Milestone Reached`
     - `Loyalty Points Redeemed`

### B. For Leafnet Support (Vendor Follow-Up)
Send these 3 quick items to Leafnet:
1. **Webhook URL Registration:** Point the order-completion webhook to our middleware endpoint and confirm `customer_id`, `order_id`, `total`, `location`, and line items (`Contents`) are included on every live payload.
2. **Consent (`opt_status`) Values:** Confirm what values `opt_status` can take when a customer opts out at the register (currently blank or `none`), so we ensure 100% compliance.
3. **Employee ID on Profile Edits:** Add `employee_id` and `employee_name` when staff add an email to an existing phone-only profile (or enable the dormant *"Customer update notification"* webhook to POST to `/webhooks/leafnet/customer-updated`).

---

## 3. The 4-Week Marketing Manager Rollout Roadmap

### Phase 1: Data Foundation & Segment Creation (Week 1, Days 1–3)
- [ ] Confirm initial full sync has completed (`GET /api/sync/history`).
- [ ] Spot-check 10 known in-store customers inside **Omnisend $\rightarrow$ Audience $\rightarrow$ Contacts** to verify their custom properties and tags appear accurately.
- [ ] Build the **8 Core Retail Segments** in Omnisend using the exact recipes in **Section 4** below.
- [ ] Pull the baseline **Phone-Only Store Audit** (`GET /api/reports/phone-only`) to benchmark how many customers at each store still need an email address.

### Phase 2: Launch the "Big 3" Core Journeys (Week 1, Day 4 – Week 2)
Start with the three highest-ROI automations and let them run cleanly for 7 days:
- [ ] **Journey 1: Retail Welcome Series** (New loyalty signups).
- [ ] **Journey 2: In-Store Post-Purchase Thank-You + Category Cross-Sell** (Fires after register checkout).
- [ ] **Journey 3: 45-Day & 90-Day Retail Win-Back** (Brings lapsed store shoppers back in).

### Phase 3: Launch Loyalty Milestones & Birthday Rewards (Week 3)
Once the Big 3 have run cleanly for a week:
- [ ] Create your reward discount codes in Leafnet POS (`REWARD5OFF`, `REWARD10PCT`, `REWARD15OFF`, `REWARD25PCT`, `BDAYGIFT`).
- [ ] **Journey 4: Marsello-Style Loyalty Milestones** (100 pts $\rightarrow$ $\$5$ off, 200 pts $\rightarrow$ 10% off, etc.).
- [ ] **Journey 5: Birthday & Loyalty Anniversary Rewards**.
- [ ] Brief store cashiers on redeeming milestone rewards at the register.

### Phase 4: Store Email Collection Contest & Attribution Review (Week 4 & Ongoing)
- [ ] Launch the **Budtender Email Capture Incentive**: use `GET /api/reports/staff-email-acquisitions` every Monday to reward staff who convert phone-only loyalty members into email subscribers.
- [ ] Review **Omnisend Revenue Attribution** (Omnisend automatically tracks which email campaigns and journeys drove in-store register orders via our `/v3/orders` feed).

---

## 4. Reproducible Omnisend Segment Recipes (Copy-Paste Rules)

To create each segment, go to **Omnisend $\rightarrow$ Audience $\rightarrow$ Segments $\rightarrow$ Create Segment $\rightarrow$ Filter Contacts** and enter the exact rule below:

### Segment 1: All Retail Customers
* **Rule:** `Tag` $\rightarrow$ `is` $\rightarrow$ `Leafnet`
* **Use for:** Sending retail-wide announcements or excluding in-store buyers from online-only promos.

### Segment 2: New In-Store Loyalty Signups (Last 7 Days)
* **Rule 1:** `Tag` $\rightarrow$ `is` $\rightarrow$ `new-loyalty-signup`
* **AND Rule 2:** `Subscription status` $\rightarrow$ `is` $\rightarrow$ `Subscribed` (Email)
* **Use for:** Onboarding check & welcome targeting.

### Segment 3: First-Time Retail Buyers
* **Rule 1:** `Tag` $\rightarrow$ `is` $\rightarrow$ `first-time-buyer` *(or Custom Property `order_count` equals `1`)*
* **Use for:** Second-visit bounce-back offers (driving habit formation from visit 1 to visit 2).

### Segment 4: Repeat Retail Regulars
* **Rule 1:** `Tag` $\rightarrow$ `is` $\rightarrow$ `repeat-customer` *(or Custom Property `order_count` is greater than or equal to `2`)*
* **AND Rule 2:** `Tag` $\rightarrow$ `is` $\rightarrow$ `active-customer`
* **Use for:** New product drops, store events, and early access.

### Segment 5: Retail VIPs (Top Spend)
* **Rule:** `Tag` $\rightarrow$ `is` $\rightarrow$ `vip` *(or Custom Property `lifetime_value` is greater than or equal to `500`)*
* **Use for:** Exclusive VIP perks, limited Craft Reserve / Connoisseur drops, and secret sales.

### Segment 6: Lapsed Customers — 45 Days (Warm Win-Back)
* **Rule 1:** `Custom Property: days_since_last_visit` $\rightarrow$ `is between` $\rightarrow$ `45` and `89`
* **AND Rule 2:** `Custom Property: order_count` $\rightarrow$ `is greater than or equal to` $\rightarrow$ `1`
* **Use for:** 45-day "We miss you" win-back flow.

### Segment 7: Lapsed Customers — 90+ Days (Deep Win-Back)
* **Rule 1:** `Tag` $\rightarrow$ `is` $\rightarrow$ `lapsed-90-days` *(or Custom Property `days_since_last_visit` is greater than or equal to `90`)*
* **Use for:** Stronger win-back incentive to prevent permanent churn.

### Segment 8: Category Buyers (Create 1 per Core Bucket)
Create a dedicated segment for each product affinity using the auto-normalized tags:
* **Gummies Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:gummies`
* **Beverages / Drinks Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:beverages`
* **Flower Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:flower`
* **Pre-Roll Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:pre-rolls`
* **Vapes / Carts Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:vapes`
* **Concentrates / Rosin Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:concentrates`
* **Edibles / Bakery Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:edibles`
* **Accessories / Gear Buyers:** `Tag` $\rightarrow$ `is` $\rightarrow$ `category:accessories`

### Segment 9: Per-Location Store Segments (Create 1 per Store)
* **Red Bank Store:** `Tag` $\rightarrow$ `is` $\rightarrow$ `store:red-bank` *(or Custom Property `home_store` equals `red-bank`)*
* **East Brainerd Store:** `Tag` $\rightarrow$ `is` $\rightarrow$ `store:east-brainerd`
* **Lee Hwy Store:** `Tag` $\rightarrow$ `is` $\rightarrow$ `store:lee-hwy`
* **Amnicola Store:** `Tag` $\rightarrow$ `is` $\rightarrow$ `store:amnicola`

---

## 5. Reproducible Omnisend Journey Blueprints (Step-by-Step)

Go to **Omnisend $\rightarrow$ Automation $\rightarrow$ Create Workflow $\rightarrow$ Create from Scratch** and configure each journey as follows:

---

### Journey 1: New Loyalty Signup Welcome Series
* **Trigger:** Custom Event $\rightarrow$ `New Loyalty Signup`
  *(Alternative trigger: Contact enters segment `New In-Store Loyalty Signups`)*
* **Exit Condition:** None (let them complete the welcome education).
* **Step 1 — Delay:** Wait `1 hour`
* **Step 2 — Email 1 ("Welcome to the Family + Your Points Balance"):**
  * **Subject:** `Welcome to Snapdragon, [[contact.first_name]]! Here's where your points stand`
  * **Body Personalization Variables to Paste:**
    - Current Points: `[[contact.custom_properties.points_balance]]`
    - Home Store: `[[contact.custom_properties.home_store]]`
    - Points Needed for First Reward ($5 Off): `[[contact.custom_properties.points_to_next_milestone]]`
* **Step 3 — Delay:** Wait `4 days`
* **Step 4 — Email 2 ("How Rewards Work + Staff Favorites"):**
  * Explain the tiers: **100 pts = $\$5$ Off**, **200 pts = 10% Off**, **300 pts = $\$15$ Off**, **500 pts = 25% Off**.

---

### Journey 2: Post-Purchase Thank-You + Category Recommendations
* **Trigger:** Custom Event $\rightarrow$ `Retail Purchase Completed`
* **Frequency Cap:** Allow contact to re-enter only once every `7 days` (so daily regulars aren't spammed after every single visit).
* **Step 1 — Delay:** Wait `2 hours` after in-store purchase.
* **Step 2 — Conditional Split (By Category Bucket):**
  * **Branch A:** `Event property: primary_category_bucket` equals `gummies` $\rightarrow$ Send Thank-You Email featuring **Infused Canned Drinks & NANO Gummies**.
  * **Branch B:** `Event property: primary_category_bucket` equals `beverages` $\rightarrow$ Send Thank-You Email featuring **Fast-Acting Gummies & Drink Additives**.
  * **Branch C:** `Event property: primary_category_bucket` equals `flower` $\rightarrow$ Send Thank-You Email featuring **Connoisseur Pre-Rolls & Hash Holes**.
  * **Branch D:** `Event property: primary_category_bucket` equals `vapes` or `concentrates` $\rightarrow$ Send Thank-You Email featuring **Solventless Rosin & Live Resin Carts**.
  * **Default Branch:** Send General Thank-You Email with **Dynamic Recommendation Headline**.
* **Dynamic Variables Available in the Email Template:**
  - Store Visited: `[[event.location]]`
  - Cashier Who Helped Them: `[[event.cashier_name]]`
  - Order Total: `$[[event.total]]`
  - Dynamic Cross-Sell Headline: `[[event.recommendation_headline]]`
  - Current Points Balance: `[[contact.custom_properties.points_balance]]`
  - Points to Next Reward: `[[contact.custom_properties.points_to_next_milestone]]`

---

### Journey 3: Lapsed Customer Win-Back (45-Day & 90-Day)
* **Trigger:** Contact enters segment $\rightarrow$ `Lapsed Customers — 45 Days`
* **Exit Condition (CRITICAL):** Custom Event `Retail Purchase Completed` *(or `Order Placed`)*. If they visit a store and buy, they immediately exit the win-back sequence!
* **Step 1 — Email 1 (Day 45 — "We Miss You at [[contact.custom_properties.home_store]]"):**
  * Remind them of their unused loyalty points: `You still have [[contact.custom_properties.points_balance]] points waiting for you!`
  * Highlight new arrivals in their favorite category: `[[contact.custom_properties.top_category]]`.
* **Step 2 — Delay:** Wait `15 days` (Day 60)
* **Step 3 — Email 2 (Day 60 — Bounce-Back Offer):**
  * Offer a "Welcome Back" perk or bonus points on their next visit.
* **Step 4 — Delay:** Wait `30 days` (Day 90)
* **Step 5 — Email 3 (Day 90 — Final Win-Back Incentive):**
  * Stronger incentive before moving them to low-frequency campaigns.

---

### Journey 4: Marsello-Style Loyalty Milestone Rewards
* **Trigger:** Custom Event $\rightarrow$ `Loyalty Milestone Reached`
* **Exit Condition:** Custom Event `Loyalty Points Redeemed`
* **Step 1 — Immediate Email ("You Unlocked a Reward: [[event.reward]]!"):**
  * **Subject:** `Congrats [[contact.first_name]]! You unlocked [[event.reward]] ({{event.points_balance}} pts)`
  * **Body Personalization Variables to Paste:**
    - Milestone Reached: `[[event.milestone_name]]`
    - Reward Value: `[[event.reward]]` (`$5 off` at 100 pts, `10% off` at 200 pts, `$15 off` at 300 pts, `25% off` at 500 pts)
    - In-Store Coupon / Discount Code: `[[event.discount_code]]`
    - Current Points Balance: `[[event.points_balance]]`
  * **Call to Action:** *"Show this email at any register (`[[contact.custom_properties.home_store]]`) to redeem your `[[event.reward]]`!"*
* **Step 2 — Delay:** Wait `14 days`
* **Step 3 — Reminder Email:** If they haven't redeemed yet, send a friendly reminder that their `[[event.reward]]` is waiting in store.

---

### Journey 5: Birthday Reward Flow
* **Trigger:** Date-based Automation $\rightarrow$ Contact's `Birthdate` (`[[contact.birthdate]]`)
* **Timing:** Trigger `7 days before` Birthday at `9:00 AM`.
* **Step 1 — Email 1 ("Happy Early Birthday! Your Birthday Gift Inside"):**
  * Send birthday voucher valid all birthday week in store.
* **Step 2 — Delay:** Wait `7 days` (On their actual birthday)
* **Step 3 — Email 2 ("Happy Birthday from Snapdragon! Don't forget your gift")**

---

### Journey 6: Inactive Subscriber Re-Engagement
* **Trigger:** Contact enters segment where `Email subscription status is Subscribed` AND `Has not opened or clicked an email in 120 days` AND `days_since_last_visit is greater than 90`.
* **Step 1 — Email 1 ("Still want to hear from us?"):**
  * Show their points balance (`[[contact.custom_properties.points_balance]]`) and ask them to click to stay subscribed.

---

## 6. Global Email Footer / Loyalty Banner Snippet

Paste this block into the footer of **every** Omnisend campaign and automation template so every email acts as a live loyalty statement:

```html
<div style="background:#f6f1e8; border:1px solid #e4d9c8; padding:16px; border-radius:8px; text-align:center;">
  <strong>Your Snapdragon Loyalty Status</strong><br/>
  Points Balance: <strong>[[contact.custom_properties.points_balance]] pts</strong> |
  Tier: <strong>[[contact.custom_properties.loyalty_tier_name]]</strong><br/>
  Only <strong>[[contact.custom_properties.points_to_next_milestone]] pts</strong> away from your next reward!
  (Home Store: [[contact.custom_properties.home_store]])
</div>
```

---

## 7. Weekly Marketing Manager Operations Checklist (15 Mins / Week)

Every Monday morning:
1. **Check Sync Health:**
   - Open `GET /api/sync/history` (or run `python -m middleware.cli sync`) to confirm daily syncs succeeded with `0` failed records.
2. **Download the Store Phone-Only Report:**
   - Run `python -m middleware.cli report-phone-only` (or open `GET /api/reports/phone-only`).
   - Share the store-by-store numbers with store managers so they know how many phone-only accounts still need an email captured at the register.
3. **Pull the Staff Email-Collection Leaderboard:**
   - Open `GET /api/reports/staff-email-acquisitions` to see which cashiers captured the most `existing_account_emails` and `new_signup_emails` during the week for staff bonuses.
4. **Review Omnisend Revenue Attribution:**
   - Check **Omnisend $\rightarrow$ Reports** to review in-store register revenue attributed to your Welcome, Post-Purchase, Win-Back, and Milestone flows.
