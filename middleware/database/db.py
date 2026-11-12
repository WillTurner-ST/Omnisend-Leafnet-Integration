import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cur = conn.cursor()

            # Table: sync_cursor
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_cursor (
                    key TEXT PRIMARY KEY,
                    val TEXT,
                    updated_at TEXT
                )
            """)

            # Table: sync_history
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT,
                    finished_at TEXT,
                    sync_type TEXT,
                    total_fetched INTEGER,
                    synced_to_omnisend INTEGER,
                    skipped_no_email INTEGER,
                    skipped_invalid_email INTEGER,
                    skipped_opted_out INTEGER,
                    failed_records INTEGER,
                    errors_json TEXT,
                    success INTEGER
                )
            """)

            # Table: processed_orders (idempotency & deduplication)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS processed_orders (
                    order_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    email TEXT,
                    phone TEXT,
                    location TEXT,
                    total_cents INTEGER,
                    cashier_id TEXT,
                    cashier_name TEXT,
                    order_created_at TEXT,
                    processed_at TEXT,
                    payload_json TEXT
                )
            """)

            # Table: phone_only_customers (in-store capture opportunities)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS phone_only_customers (
                    leafnet_customer_id TEXT PRIMARY KEY,
                    customer_name TEXT,
                    phone TEXT,
                    favorite_location TEXT,
                    order_count INTEGER,
                    lifetime_spend REAL,
                    last_seen_at TEXT,
                    updated_at TEXT
                )
            """)

            # Table: customer_sync_state (tracks points milestones, welcome journey, & email state)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS customer_sync_state (
                    leafnet_customer_id TEXT PRIMARY KEY,
                    email TEXT,
                    phone TEXT,
                    last_points_balance REAL DEFAULT 0.0,
                    highest_milestone_notified REAL DEFAULT 0.0,
                    welcome_sent INTEGER DEFAULT 0,
                    first_synced_at TEXT,
                    updated_at TEXT
                )
            """)

            # Table: employee_email_logs (staff attribution for Goal 3)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS employee_email_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT,
                    old_email TEXT,
                    new_email TEXT,
                    employee_id TEXT,
                    employee_name TEXT,
                    location TEXT,
                    action_type TEXT, -- 'email_add_existing', 'email_capture_new_signup', 'email_change'
                    timestamp TEXT
                )
            """)

            conn.commit()

    # Cursor management
    def get_cursor(self, key: str = "last_leafnet_updated_at") -> Optional[str]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT val FROM sync_cursor WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["val"] if row else None

    def set_cursor(self, key: str, val: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO sync_cursor (key, val, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET val = excluded.val, updated_at = excluded.updated_at
            """, (key, val, now))
            conn.commit()

    # Sync History
    def record_sync_start(self, sync_type: str = "incremental") -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO sync_history (started_at, sync_type, success)
                VALUES (?, ?, 0)
            """, (now, sync_type))
            conn.commit()
            return cur.lastrowid

    def record_sync_finish(
        self,
        sync_id: int,
        total_fetched: int,
        synced_to_omnisend: int,
        skipped_no_email: int,
        skipped_invalid_email: int,
        skipped_opted_out: int,
        failed_records: int,
        errors: List[str],
        success: bool,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE sync_history
                SET finished_at = ?,
                    total_fetched = ?,
                    synced_to_omnisend = ?,
                    skipped_no_email = ?,
                    skipped_invalid_email = ?,
                    skipped_opted_out = ?,
                    failed_records = ?,
                    errors_json = ?,
                    success = ?
                WHERE id = ?
            """, (
                now,
                total_fetched,
                synced_to_omnisend,
                skipped_no_email,
                skipped_invalid_email,
                skipped_opted_out,
                failed_records,
                json.dumps(errors),
                1 if success else 0,
                sync_id,
            ))
            conn.commit()

    def get_latest_sync_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM sync_history ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["errors"] = json.loads(d.get("errors_json") or "[]")
                results.append(d)
            return results

    # Customer Sync State (Milestone & Welcome tracking)
    def get_customer_sync_state(self, leafnet_customer_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM customer_sync_state WHERE leafnet_customer_id = ?",
                (str(leafnet_customer_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_customer_sync_state_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        if not phone:
            return None
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM customer_sync_state WHERE phone = ? LIMIT 1",
                (phone,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_customer_sync_state(
        self,
        leafnet_customer_id: str,
        email: str,
        phone: str,
        points_balance: float,
        highest_milestone_notified: float,
        welcome_sent: bool = False,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO customer_sync_state (
                    leafnet_customer_id, email, phone,
                    last_points_balance, highest_milestone_notified,
                    welcome_sent, first_synced_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(leafnet_customer_id) DO UPDATE SET
                    email = excluded.email,
                    phone = excluded.phone,
                    last_points_balance = excluded.last_points_balance,
                    highest_milestone_notified = MAX(customer_sync_state.highest_milestone_notified, excluded.highest_milestone_notified),
                    welcome_sent = MAX(customer_sync_state.welcome_sent, excluded.welcome_sent),
                    updated_at = excluded.updated_at
            """, (
                str(leafnet_customer_id),
                email,
                phone or "",
                points_balance,
                highest_milestone_notified,
                1 if welcome_sent else 0,
                now,
                now,
            ))
            conn.commit()

    # Deduplication of orders
    def is_order_processed(self, order_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM processed_orders WHERE order_id = ?", (order_id,))
            return cur.fetchone() is not None

    def record_processed_order(
        self,
        order_id: str,
        customer_id: Optional[str],
        email: Optional[str],
        phone: Optional[str],
        location: Optional[str],
        total_cents: int,
        cashier_id: Optional[str],
        cashier_name: Optional[str],
        order_created_at: Optional[str],
        payload: dict,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO processed_orders (
                    order_id, customer_id, email, phone, location,
                    total_cents, cashier_id, cashier_name,
                    order_created_at, processed_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                str(customer_id) if customer_id else "",
                email or "",
                phone or "",
                location or "",
                total_cents,
                cashier_id or "",
                cashier_name or "",
                order_created_at or "",
                now,
                json.dumps(payload),
            ))
            conn.commit()

    def get_latest_order_for_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM processed_orders
                WHERE customer_id = ?
                ORDER BY processed_at DESC LIMIT 1
            """, (str(customer_id),))
            row = cur.fetchone()
            return dict(row) if row else None

    # Phone-only customers
    def get_phone_only_customer(self, leafnet_customer_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM phone_only_customers WHERE leafnet_customer_id = ?",
                (str(leafnet_customer_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_phone_only_customer(
        self,
        leafnet_customer_id: str,
        customer_name: str,
        phone: str,
        favorite_location: str,
        order_count: int,
        lifetime_spend: float,
        last_seen_at: str,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO phone_only_customers (
                    leafnet_customer_id, customer_name, phone, favorite_location,
                    order_count, lifetime_spend, last_seen_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(leafnet_customer_id) DO UPDATE SET
                    customer_name = excluded.customer_name,
                    phone = excluded.phone,
                    favorite_location = excluded.favorite_location,
                    order_count = excluded.order_count,
                    lifetime_spend = excluded.lifetime_spend,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
            """, (
                str(leafnet_customer_id),
                customer_name or "",
                phone or "",
                favorite_location or "Unknown",
                order_count,
                lifetime_spend,
                last_seen_at or "",
                now,
            ))
            conn.commit()

    def remove_phone_only_customer(self, leafnet_customer_id: str):
        """If customer now has an email, remove them from phone-only list."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM phone_only_customers WHERE leafnet_customer_id = ?", (str(leafnet_customer_id),))
            conn.commit()

    def get_phone_only_by_store(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COALESCE(NULLIF(favorite_location, ''), 'Unknown') AS store_location,
                    COUNT(*) as phone_only_count,
                    SUM(order_count) as total_orders,
                    ROUND(SUM(lifetime_spend), 2) as total_unreached_spend
                FROM phone_only_customers
                GROUP BY store_location
                ORDER BY phone_only_count DESC
            """)
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_synced_count_by_store(self) -> Dict[str, int]:
        """Counts total processed orders or synced profiles by location for capture rate calculations."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM customer_sync_state")
            row = cur.fetchone()
            return {"total_synced": row["cnt"] if row else 0}

    # Employee email change logs
    def record_employee_email_change(
        self,
        customer_id: str,
        old_email: Optional[str],
        new_email: str,
        employee_id: Optional[str],
        employee_name: Optional[str],
        location: Optional[str],
        action_type: str = "email_change",
        timestamp: Optional[str] = None,
    ):
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO employee_email_logs (
                    customer_id, old_email, new_email, employee_id,
                    employee_name, location, action_type, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(customer_id),
                old_email or "",
                new_email,
                employee_id or "",
                employee_name or "Unknown Employee",
                location or "",
                action_type,
                ts,
            ))
            conn.commit()

    def get_employee_email_acquisitions(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COALESCE(NULLIF(employee_id, ''), 'Unknown') as employee_id,
                    COALESCE(NULLIF(employee_name, ''), 'Unknown') as employee_name,
                    COUNT(*) as emails_collected_count,
                    SUM(CASE WHEN action_type = 'email_add_existing' THEN 1 ELSE 0 END) as existing_account_emails,
                    SUM(CASE WHEN action_type = 'email_capture_new_signup' THEN 1 ELSE 0 END) as new_signup_emails
                FROM employee_email_logs
                GROUP BY employee_id, employee_name
                ORDER BY emails_collected_count DESC
            """)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
