# Coolify Deployment & Testing Guide
## Leafnet / NocoDB into Omnisend Middleware

This guide walks you through deploying this middleware onto **Coolify**, connecting it to **NocoDB**, setting up SSL and domain routing for **Leafnet webhooks**, and performing live testing.

---

## 1. Prerequisites Checklist

Before deploying in Coolify, ensure you have:
1. **Coolify Instance** up and running on your VPS/server.
2. **Domain/Subdomain** pointed to your Coolify server's IP address (e.g. DNS A Record: `middleware.yourdomain.com` $\rightarrow$ Server IP).
3. **NocoDB Details:**
   - URL: Either internal Docker URL (if NocoDB is also in Coolify, e.g. `http://nocodb:8080`) or public URL (e.g. `https://nocodb.yourdomain.com`).
   - `xc-token`: Generated in NocoDB (User Settings $\rightarrow$ API Tokens).
   - `tableId`: The ID of the `Leafnet Customers` table.
4. **Omnisend API Key:** Generated in Omnisend (Store Settings $\rightarrow$ API Keys).

---

## 2. Deploying on Coolify (Step-by-Step)

### Deploy via Git Repository
1. Commit and push your code to your Git server (GitHub, GitLab, or Gitea):
   ```bash
   git add .
   git commit -m "Add Leafnet-Omnisend middleware"
   git push origin main
   ```
2. Log into your **Coolify Dashboard**.
3. Select your **Project** and **Environment** (e.g. Production).
4. Click **+ New Resource** $\rightarrow$ **Application**.
5. Select **Public Repository** or **Private Git Repository** (choose your Git provider).
6. Enter your repository URL (e.g. `https://github.com/your-org/leafnet-omnisend-middleware` or your internal Gitea URL) and branch `main`.
7. **Build Pack:** Coolify detects the `Dockerfile` because the repository has no Compose file.
   - Set the Build Pack to **Dockerfile** if the scan has not already selected it.
   - **Port Exposes:** Enter `18743`.

---

## 3. Configuring Environment Variables in Coolify

In your application's settings in Coolify, go to the **Environment Variables** tab and add the following keys:

```env
# Server Configuration
HOST=0.0.0.0
PORT=18743
ENVIRONMENT=production
LOG_LEVEL=INFO
SYNC_INTERVAL_HOURS=24
DB_PATH=/app/data/middleware.db

# Omnisend API Configuration
OMNISEND_API_KEY=your_actual_omnisend_api_key
OMNISEND_BASE_URL=https://api.omnisend.com/api
OMNISEND_API_VERSION=2026-03-15

# NocoDB Configuration
# If NocoDB is in the same Coolify Docker network, you can use: http://<nocodb-container-name>:8080
# Or use the public domain:
NOCODB_API_URL=https://nocodb.yourdomain.com
NOCODB_API_TOKEN=your_actual_nocodb_xc_token
NOCODB_TABLE_ID=your_customers_table_id
NOCODB_PAGE_SIZE=100

# Leafnet API Configuration
LEAFNET_API_URL=https://snapdragon-hemp.haimenu.com/api/
LEAFNET_API_KEY=your_leafnet_api_key_here
LEAFNET_FOLDER_NAME=snapdragon-hemp

# Segmentation. Loyalty stays off for the first deploy.
VIP_SPEND_THRESHOLD=500.0
CONTACTS_ONLY=true
LOYALTY_ENABLED=false

# Optional Webhook Security
# If set, incoming webhooks must include header: X-Webhook-Secret: <your_secret>
# Leave blank initially for easy testing with Leafnet
WEBHOOK_SECRET=
```

---

## 4. Persistent Storage (Crucial for SQLite DB)

To ensure your SQLite database (`middleware.db` storing order deduplication, sync cursor, and audit logs) persists across container restarts and redeployments:

1. In Coolify, open your application $\rightarrow$ **Storages** tab.
2. Click **+ Add Storage**.
3. Set:
   - **Destination Path:** `/app/data`
   - **Volume Name:** `middleware-data` (or choose a host mount path like `/var/lib/docker/volumes/middleware-data`)
4. Click **Save**.

---

## 5. Domain & Automatic SSL Setup

1. In Coolify, go to the **Configuration / General** tab.
2. In the **Domains** field, enter your public domain with `https://`:
   ```
   https://middleware.yourdomain.com
   ```
3. Coolify (via Traefik / Caddy) will automatically request and install a free Let's Encrypt SSL certificate.
4. Click **Save**.

---

## 6. Deploy & Verify

1. Click **Deploy** at the top right of the Coolify dashboard.
2. Check the build and container logs. Once complete, Coolify will show container status as **Healthy** (utilizing our Dockerfile `HEALTHCHECK`).
3. Open your browser and navigate to:
   - `https://middleware.yourdomain.com/health` $\rightarrow$ should return `{"status":"healthy", ...}`
   - `https://middleware.yourdomain.com/docs` $\rightarrow$ launches interactive OpenAPI Swagger documentation!

---

## 7. Live Testing Procedure

Now that the middleware is running live on Coolify, test each component:

### Test 1: Verify NocoDB Connection & Trigger Test Sync
Run this from your terminal or directly in the `/docs` UI:
```bash
curl -X POST "https://middleware.yourdomain.com/api/sync/run?full=false"
```
**Expected Response:**
```json
{
  "total_fetched": 3,
  "synced_to_omnisend": 2,
  "skipped_no_email": 1,
  "failed_records": 0,
  "success": true
}
```
*Verify in Omnisend:* Open Omnisend $\rightarrow$ **Audience** $\rightarrow$ **Contacts** and confirm the contacts appear with tags (`Leafnet`, `retail`, `store:...`) and custom properties.

---

### Test 2: Simulate Live Leafnet Order Webhook
Test that an incoming retail sale turns into an Omnisend purchase and fires the thank-you automation:

```bash
curl -X POST "https://middleware.yourdomain.com/webhooks/leafnet/order-completed" \
  -H "Content-Type: application/json" \
  -d '{
    "Order Id": "#999001",
    "customer_id": "20854",
    "email": "your_test_email@example.com",
    "phone": "(423) 555-0199",
    "Created": "2026-11-10 12:00:00",
    "Location": "red-bank",
    "Subtotal": "35.00",
    "Discounts": "0.00",
    "Tax and Fees": "3.25",
    "Total": "38.25",
    "Contents": [
      {
        "item_id": "501",
        "name": "Snapdragon Gummies 12pk",
        "qty": 1,
        "unit_cost": "35.00",
        "macros": [
          {"type": "Category", "value": "Snapdragon Gummies"}
        ]
      }
    ]
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "order_id": "999001",
  "has_email": true,
  "total_cents": 3825,
  "categories": ["Snapdragon Gummies"],
  "category_buckets": ["gummies"],
  "recommended_category_bucket": "beverages",
  "omnisend_order": {"status": "created", ...},
  "omnisend_event": {"status": "success", ...}
}
```

*Verify in Omnisend:*
1. **Live Event Received:** In Omnisend, go to **Automation** $\rightarrow$ **Custom Events** $\rightarrow$ verify `Retail Purchase Completed` appears.
2. **Order Placed:** Go to the contact profile for `your_test_email@example.com` $\rightarrow$ verify the order for `$38.25` is recorded under Order History!

---

### Test 3: Test Webhook Deduplication
Send the exact same curl command from Test 2 again with `#999001`.
**Expected Response:**
```json
{
  "status": "skipped",
  "reason": "duplicate_order",
  "order_id": "999001"
}
```
*(Confirms that double-triggers never spam customers with multiple emails).*

---

### Test 4: Give Leafnet the Live Webhook URL
Once Test 2 succeeds, provide the Leafnet technical contact with:
```
Webhook URL: https://middleware.yourdomain.com/webhooks/leafnet/order-completed
Method: POST
Payload: Standard JSON (Order Id, customer_id, email, phone, Total, Location, Contents)
```

---

## 8. Summary of Active URLs on Coolify

| Purpose | Endpoint |
|---|---|
| **Health Check** | `GET https://middleware.yourdomain.com/health` |
| **Interactive Docs (Swagger UI)** | `GET https://middleware.yourdomain.com/docs` |
| **Leafnet Order Webhook (Register this with Leafnet)** | `POST https://middleware.yourdomain.com/webhooks/leafnet/order-completed` |
| **Leafnet Customer Update Webhook** | `POST https://middleware.yourdomain.com/webhooks/leafnet/customer-updated` |
| **Manual Trigger Customer Sync** | `POST https://middleware.yourdomain.com/api/sync/run?full=false` |
| **In-Store Phone-Only Store Report** | `GET https://middleware.yourdomain.com/api/reports/phone-only` |
| **Staff Email Acquisition Leaderboard** | `GET https://middleware.yourdomain.com/api/reports/staff-email-acquisitions` |
| **Customer Parity Verification** | `GET https://middleware.yourdomain.com/api/verify/customer/{id}` |
