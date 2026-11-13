import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from middleware.config import settings
from middleware.clients.omnisend_client import OmnisendClient
from middleware.clients.nocodb_client import NocoDBClient
from middleware.clients.leafnet_client import LeafnetClient
from middleware.database.db import Database
from middleware.models.leafnet import LeafnetOrderWebhookPayload
from middleware.models.omnisend import (
    OmnisendOrderPayload,
    OmnisendOrderProduct,
    OmnisendEventPayload,
    OmnisendContactPayload,
    OmnisendIdentifier,
    OmnisendChannels,
    OmnisendChannelStatus,
)
from middleware.services.contact_sync_service import ContactSyncService
from middleware.services.category_mapper import CategoryMapper

logger = logging.getLogger("middleware.webhook_service")


class WebhookService:
    def __init__(
        self,
        omnisend_client: Optional[OmnisendClient] = None,
        nocodb_client: Optional[NocoDBClient] = None,
        leafnet_client: Optional[LeafnetClient] = None,
        database: Optional[Database] = None,
    ):
        self.omnisend = omnisend_client or OmnisendClient()
        self.nocodb = nocodb_client or NocoDBClient()
        self.leafnet = leafnet_client or LeafnetClient()
        self.db = database or Database(settings.db_path)

    @staticmethod
    def parse_iso_datetime(raw_dt: Optional[str]) -> str:
        """Converts raw Leafnet datetime string (e.g. '2026-07-05 18:48:17') to ISO-8601."""
        if not raw_dt:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = str(raw_dt).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def resolve_customer_email(
        self,
        payload: LeafnetOrderWebhookPayload,
        clean_phone: str,
    ) -> str:
        """
        Goal 2 & Step 5: Match customer by leafnet_customer_id, then email, then phone.
        If webhook payload omits email, checks local sync cache, NocoDB, or Leafnet API.
        """
        raw_email = (payload.email or "").strip().lower()
        if raw_email and "@" in raw_email and "." in raw_email.split("@")[-1]:
            return raw_email

        cust_id = str(payload.customer_id or "").strip()

        # 1. Check local SQLite sync state by customer_id
        if cust_id:
            state = self.db.get_customer_sync_state(cust_id)
            if state and state.get("email"):
                return state["email"].strip().lower()

        # 2. Check local SQLite sync state by phone
        if clean_phone:
            state = self.db.get_customer_sync_state_by_phone(clean_phone)
            if state and state.get("email"):
                return state["email"].strip().lower()

        # 3. Fallback to NocoDB lookup if configured
        if cust_id and settings.nocodb_api_token and settings.nocodb_table_id:
            try:
                res = await self.nocodb.get_records_page(
                    limit=1,
                    where_clause=f"(leafnet_customer_id,eq,{cust_id})",
                )
                if res.list:
                    noco_email = str(res.list[0].get("email") or "").strip().lower()
                    if "@" in noco_email:
                        return noco_email
            except Exception as e:
                logger.debug(f"NocoDB fallback email lookup skipped: {e}")

        return ""

    async def process_order_completed(self, payload: LeafnetOrderWebhookPayload) -> Dict[str, Any]:
        """
        Handles the real-time order-completion webhook from Leafnet POS (Goals 2, 3, 4, 5, 6):
        1. Deduplication check by order_id
        2. Resolves customer email (direct payload -> customer_id -> phone)
        3. Converts dollar amounts to integer cents & posts to Omnisend Orders API
        4. Enriches with CategoryMapper recommendations & triggers 'Retail Purchase Completed' event
        5. Updates contact properties & category/store tags in real-time
        6. Tracks staff email attribution (Goal 3)
        """
        order_id = payload.clean_order_id
        if not order_id:
            raise ValueError("Order payload missing order_id")

        # 1. Deduplication Check
        if self.db.is_order_processed(order_id):
            logger.info(f"Order #{order_id} already processed. Skipping duplicate.")
            return {
                "status": "skipped",
                "reason": "duplicate_order",
                "order_id": order_id,
            }

        phone = ContactSyncService.clean_phone_number(payload.phone)
        email = await self.resolve_customer_email(payload, phone)
        has_valid_email = bool(email and "@" in email and "." in email.split("@")[-1])
        cust_id = str(payload.customer_id or "").strip()

        # Line items mapping for Omnisend Order
        products: List[OmnisendOrderProduct] = []
        if payload.items:
            for item in payload.items:
                unit_price_cents = int(round(item.price_as_float * 100))
                qty = int(float(item.qty)) if item.qty else 1
                products.append(
                    OmnisendOrderProduct(
                        productID=str(item.item_id),
                        title=item.name,
                        quantity=qty,
                        price=unit_price_cents,
                        sku=item.barcode or str(item.item_id),
                        category=item.resolved_category,
                    )
                )

        order_dt_iso = self.parse_iso_datetime(payload.created)
        cashier_id = payload.staff_account_id
        cashier_name = payload.staff_account_name
        categories = payload.categories
        primary_category = categories[0] if categories else "General"
        rec_meta = CategoryMapper.get_recommendations(categories)

        omnisend_order_result = None
        omnisend_event_result = None

        # 2. Process with Omnisend if customer has an email
        if has_valid_email:
            # Goal 3: Staff attribution tracking
            if cust_id:
                prior_phone_only = self.db.get_phone_only_customer(cust_id)
                prior_state = self.db.get_customer_sync_state(cust_id)
                if prior_phone_only:
                    # Existing phone-only customer gained an email on this order!
                    self.db.record_employee_email_change(
                        customer_id=cust_id,
                        old_email="",
                        new_email=email,
                        employee_id=cashier_id,
                        employee_name=cashier_name or "POS Staff",
                        location=payload.location,
                        action_type="email_add_existing",
                        timestamp=payload.created,
                    )
                    self.db.remove_phone_only_customer(cust_id)
                elif not prior_state and (cashier_id or cashier_name):
                    # Brand-new account with email on first sale
                    self.db.record_employee_email_change(
                        customer_id=cust_id,
                        old_email="",
                        new_email=email,
                        employee_id=cashier_id,
                        employee_name=cashier_name or "POS Staff",
                        location=payload.location,
                        action_type="email_capture_new_signup",
                        timestamp=payload.created,
                    )

            # Build Omnisend Order (for revenue attribution & order history)
            omnisend_order = OmnisendOrderPayload(
                orderID=order_id,
                email=email,
                phone=phone or None,
                currency="USD",
                orderSum=payload.total_cents,
                subTotalSum=payload.subtotal_cents,
                discountSum=payload.discount_cents,
                taxSum=payload.tax_cents,
                paymentStatus="paid",
                fulfillmentStatus="fulfilled",
                createdAt=order_dt_iso,
                products=products,
            )

            if settings.contacts_only:
                logger.info(
                    f"Contacts-only mode: skipped Omnisend order and purchase event for #{order_id}."
                )
                omnisend_order_result = {"status": "skipped", "reason": "contacts_only"}
                omnisend_event_result = {"status": "skipped", "reason": "contacts_only"}
            else:
                try:
                    omnisend_order_result = await self.omnisend.create_order(omnisend_order)
                    logger.info(f"Posted order #{order_id} to Omnisend orders API successfully.")
                except Exception as e:
                    logger.warning(f"Failed to post order #{order_id} to Omnisend orders API: {e}")

                # Build and trigger Custom Event for instant post-purchase journey & recommendations (Goal 2 & Goal 6)
                custom_event = OmnisendEventPayload(
                    eventName="Retail Purchase Completed",
                    email=email,
                    phone=phone or None,
                    eventID=f"leafnet-order-{order_id}",
                    properties={
                        "order_id": order_id,
                        "leafnet_customer_id": cust_id,
                        "location": payload.location or "Store",
                        "total": payload.float_total,
                        "total_cents": payload.total_cents,
                        "categories": categories,
                        "primary_category": primary_category,
                        "primary_category_bucket": rec_meta["primary_bucket"],
                        "category_buckets": rec_meta["all_buckets"],
                        "recommended_category_bucket": rec_meta["recommended_bucket"],
                        "recommendation_headline": rec_meta["recommendation_headline"],
                        "suggested_categories": rec_meta["suggested_categories"],
                        "cashier_name": cashier_name or "Staff",
                        "cashier_id": cashier_id,
                        "item_count": sum([p.quantity for p in products]) if products else 1,
                        "created_at": payload.created or "",
                    },
                )

                try:
                    omnisend_event_result = await self.omnisend.trigger_event(custom_event)
                    logger.info(f"Triggered custom event for order #{order_id} in Omnisend.")
                except Exception as e:
                    logger.warning(f"Failed to trigger custom event for order #{order_id}: {e}")

            # Real-time contact update in Omnisend (Goal 4 & Goal 5)
            try:
                identifiers = [
                    OmnisendIdentifier(
                        type="email",
                        id=email,
                        channels=OmnisendChannels(email=OmnisendChannelStatus(status="subscribed")),
                    )
                ]
                if phone:
                    identifiers.append(OmnisendIdentifier(type="phone", id=phone))

                contact_tags = ["retail", "leafnet", "active-customer"]
                if payload.location:
                    contact_tags.append(f"store:{payload.location.strip().lower()}")
                for b in rec_meta["all_buckets"]:
                    if b != "general":
                        contact_tags.append(f"category:{b}")

                contact_update = OmnisendContactPayload(
                    identifiers=identifiers,
                    firstName=payload.first_name or None,
                    lastName=payload.last_name or None,
                    tags=contact_tags,
                    customProperties={
                        "leafnet_customer_id": cust_id,
                        "last_visit_date": payload.created or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "days_since_last_visit": 0,
                        "home_store": payload.location or "",
                        "top_category": primary_category,
                        "top_category_bucket": rec_meta["primary_bucket"],
                        "last_order_id": order_id,
                        "last_order_total": payload.float_total,
                    },
                )
                await self.omnisend.upsert_contact(contact_update)
            except Exception as e:
                logger.warning(f"Failed real-time contact update for {email}: {e}")

        else:
            # Customer has no email -> Record phone-only customer activity (Goal 3)
            logger.info(f"Order #{order_id} was placed by customer without email. Recording in store capture list.")
            if cust_id or phone:
                self.db.upsert_phone_only_customer(
                    leafnet_customer_id=cust_id or f"phone_{phone}",
                    customer_name=f"{payload.first_name or ''} {payload.last_name or ''}".strip(),
                    phone=payload.phone or "",
                    favorite_location=payload.location or "Store",
                    order_count=1,
                    lifetime_spend=payload.float_total,
                    last_seen_at=payload.created or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                )

        # 3. Record processed order in SQLite database for deduplication and attribution
        self.db.record_processed_order(
            order_id=order_id,
            customer_id=cust_id,
            email=email if has_valid_email else None,
            phone=phone if phone else None,
            location=payload.location,
            total_cents=payload.total_cents,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            order_created_at=payload.created,
            payload=payload.model_dump(exclude_none=True),
        )

        return {
            "status": "success",
            "order_id": order_id,
            "has_email": has_valid_email,
            "resolved_email": email if has_valid_email else None,
            "total_cents": payload.total_cents,
            "categories": categories,
            "category_buckets": rec_meta["all_buckets"],
            "recommended_category_bucket": rec_meta["recommended_bucket"],
            "cashier": cashier_name,
            "omnisend_order": omnisend_order_result,
            "omnisend_event": omnisend_event_result,
        }
