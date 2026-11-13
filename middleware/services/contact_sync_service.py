import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from middleware.config import settings
from middleware.clients.nocodb_client import NocoDBClient
from middleware.clients.omnisend_client import OmnisendClient
from middleware.database.db import Database
from middleware.models.nocodb import NocoDBCustomerRecord
from middleware.models.omnisend import (
    OmnisendContactPayload,
    OmnisendIdentifier,
    OmnisendChannels,
    OmnisendChannelStatus,
    OmnisendEventPayload,
)
from middleware.models.internal import SyncRunSummary
from middleware.services.category_mapper import CategoryMapper
from middleware.services.loyalty_service import LoyaltyService

logger = logging.getLogger("middleware.contact_sync_service")


class ContactSyncService:
    def __init__(
        self,
        nocodb_client: Optional[NocoDBClient] = None,
        omnisend_client: Optional[OmnisendClient] = None,
        database: Optional[Database] = None,
        loyalty_service: Optional[LoyaltyService] = None,
    ):
        self.nocodb = nocodb_client or NocoDBClient()
        self.omnisend = omnisend_client or OmnisendClient()
        self.db = database or Database(settings.db_path)
        self.loyalty = loyalty_service or LoyaltyService(omnisend_client=self.omnisend)

    @staticmethod
    def clean_phone_number(raw_phone: Optional[str]) -> str:
        """Standardizes phone number digits into E.164 (+1...) or clean format."""
        if not raw_phone:
            return ""
        digits = re.sub(r"\D", "", str(raw_phone))
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        return digits

    @staticmethod
    def clean_birthdate(raw_date: Optional[str]) -> Optional[str]:
        """Normalizes birth date to YYYY-MM-DD if valid."""
        if not raw_date:
            return None
        raw = str(raw_date).strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
        return m.group(1) if m else None

    @staticmethod
    def extract_month_day(iso_date: Optional[str]) -> str:
        """Extracts MM-DD from an ISO date or datetime string for birthday/anniversary segments."""
        if not iso_date:
            return ""
        m = re.search(r"\b\d{4}-(\d{2}-\d{2})\b", str(iso_date))
        return m.group(1) if m else ""

    @staticmethod
    def is_recent_signup(signup_date_str: Optional[str], days: int = 7) -> bool:
        """Checks if signup_date is within the last N days for Goal 5 & Goal 6 Welcome Series."""
        if not signup_date_str:
            return False
        raw = str(signup_date_str).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                delta = (now - dt).days
                return 0 <= delta <= days
            except ValueError:
                continue
        return False

    @staticmethod
    def is_opted_out(opt_status: Optional[str]) -> bool:
        """
        Determines whether customer explicitly opted out.
        Leafnet values: blank, 'none', or potential opt-outs.
        """
        if not opt_status:
            return False
        val = str(opt_status).strip().lower()
        return val in ("opt_out", "opted_out", "unsubscribe", "unsubscribed", "do_not_email")

    def build_omnisend_contact(self, customer: NocoDBCustomerRecord) -> OmnisendContactPayload:
        """Transforms a NocoDB customer record into an Omnisend Contact Payload covering Goals 1, 4, 5, 6."""
        clean_email = customer.clean_email
        clean_phone = self.clean_phone_number(customer.phone)
        opt_out = self.is_opted_out(customer.opt_status)

        # Identifiers
        identifiers: List[OmnisendIdentifier] = [
            OmnisendIdentifier(
                type="email",
                id=clean_email,
                channels=OmnisendChannels(
                    email=OmnisendChannelStatus(
                        status="unsubscribed" if opt_out else "subscribed"
                    )
                ),
            )
        ]

        if clean_phone:
            # Contacts-only import stores the number without opting the customer into SMS.
            sms_status = "nonSubscribed" if settings.contacts_only or opt_out else "subscribed"
            identifiers.append(
                OmnisendIdentifier(
                    type="phone",
                    id=clean_phone,
                    channels=OmnisendChannels(
                        sms=OmnisendChannelStatus(status=sms_status)
                    ),
                )
            )

        # Tags for Omnisend Segments & Journeys (Goal 5 & Goal 6)
        tags = ["retail", "Leafnet"]

        # Store tag (Per-location segments)
        home_store = (customer.favorite_location or "").strip()
        if home_store:
            tags.append(f"store:{home_store.lower()}")

        # Signup date. The loyalty welcome tag is only applied when loyalty is on.
        signup_dt = customer.leafnet_created_at or customer.first_visit or ""
        if settings.loyalty_enabled and self.is_recent_signup(signup_dt, days=7):
            tags.append("new-loyalty-signup")

        # Buyer frequency tags (First-time vs Repeat)
        order_count = customer.int_order_count
        if order_count == 1:
            tags.append("first-time-buyer")
        elif order_count >= 2:
            tags.append("repeat-customer")

        # VIP tag
        lifetime_spend = customer.float_lifetime_spend
        is_vip = lifetime_spend >= settings.vip_spend_threshold
        if is_vip:
            tags.append("vip")

        # Lapsed / winback tags
        days_since_visit = customer.int_days_since_last_visit
        if days_since_visit >= 90:
            tags.append("lapsed-90-days")
            tags.append("lapsed-45-days")
        elif days_since_visit >= 45:
            tags.append("lapsed-45-days")
        elif order_count >= 1:
            tags.append("active-customer")

        # Category buyer tags (gummies vs beverages vs flower, etc.)
        top_cats = customer.top_categories_list
        primary_cat = customer.favorite_category or (top_cats[0] if top_cats else "")
        primary_bucket = CategoryMapper.normalize_bucket(primary_cat) if primary_cat else ""
        if primary_bucket and primary_bucket != "general":
            tags.append(f"category:{primary_bucket}")
        for cat in top_cats:
            bucket = CategoryMapper.normalize_bucket(cat)
            tag_name = f"category:{bucket}"
            if bucket != "general" and tag_name not in tags:
                tags.append(tag_name)

        points = customer.float_points
        milestone_progress = None
        if settings.loyalty_enabled:
            for ms in LoyaltyService.MILESTONES:
                threshold_int = int(ms["threshold"])
                if points >= ms["threshold"]:
                    tags.append(f"loyalty-tier-{threshold_int}")
            milestone_progress = LoyaltyService.get_milestone_progress(points)

        clean_bday = self.clean_birthdate(customer.birth_date)

        # Custom Properties (Goals 1, 4, 5, 6)
        custom_props: Dict[str, Any] = {
            "leafnet_customer_id": str(customer.leafnet_customer_id or ""),
            "phone": customer.phone or "",
            "birthday": clean_bday or "",
            "birthday_month_day": self.extract_month_day(clean_bday),
            "home_store": home_store,
            "signup_date": signup_dt,
            "signup_anniversary_month_day": self.extract_month_day(signup_dt),
            "signup_source": customer.resolved_signup_source,
            "last_visit_date": customer.last_visit or "",
            "days_since_last_visit": days_since_visit,
            "visit_count": customer.int_visit_count,
            "visit_frequency_days": round(customer.float_visit_frequency_days, 1),
            "order_count": order_count,
            "lifetime_value": round(lifetime_spend, 2),
            "average_spend": round(customer.float_average_order_value, 2),
            "is_vip": is_vip,
            "top_category": primary_cat,
            "top_category_bucket": primary_bucket,
            "top_categories": ", ".join(top_cats),
            "opt_status": customer.opt_status or "none",
        }
        if milestone_progress is not None:
            custom_props.update({
                "points_balance": round(points, 2),
                "loyalty_tier_name": milestone_progress["loyalty_tier_name"],
                "available_reward": milestone_progress["available_reward"],
                "next_milestone_points": milestone_progress["next_milestone_points"],
                "points_to_next_milestone": milestone_progress["points_to_next_milestone"],
            })

        return OmnisendContactPayload(
            identifiers=identifiers,
            firstName=customer.resolved_first_name or None,
            lastName=customer.resolved_last_name or None,
            birthdate=clean_bday,
            tags=tags,
            customProperties=custom_props,
        )

    async def run_sync(self, full_sync: bool = False) -> SyncRunSummary:
        """
        Executes customer sync from NocoDB to Omnisend.
        Handles:
        - Upserting contacts & custom metrics (Goals 1 & 4)
        - Detecting existing phone-only customers who added an email (Goal 3)
        - Firing Welcome & Loyalty Milestone journeys (Goal 6)
        """
        started_at = datetime.now(timezone.utc)
        sync_type = "full" if full_sync else "incremental"
        sync_id = self.db.record_sync_start(sync_type=sync_type)

        since_timestamp = None
        if not full_sync:
            since_timestamp = self.db.get_cursor("last_leafnet_updated_at")
            logger.info(f"Incremental sync requested. Cursor since: {since_timestamp}")

        errors: List[str] = []
        total_fetched = 0
        synced_count = 0
        skipped_no_email = 0
        skipped_invalid_email = 0
        skipped_opted_out = 0
        new_signups_triggered = 0
        milestones_triggered = 0
        existing_emails_captured = 0
        failed_records = 0
        latest_updated_at = since_timestamp

        try:
            records = await self.nocodb.fetch_all_records(
                since_timestamp=since_timestamp,
                batch_size=settings.nocodb_page_size,
            )
            total_fetched = len(records)

            for raw_row in records:
                customer = NocoDBCustomerRecord(**raw_row)

                # Track latest updated_at for cursor
                if customer.leafnet_updated_at:
                    if not latest_updated_at or customer.leafnet_updated_at > latest_updated_at:
                        latest_updated_at = customer.leafnet_updated_at

                cust_id = str(customer.leafnet_customer_id or customer.Id or "")

                # Case 1: No email provided -> Track in phone-only audit table
                if not customer.email or not str(customer.email).strip():
                    skipped_no_email += 1
                    if cust_id:
                        self.db.upsert_phone_only_customer(
                            leafnet_customer_id=cust_id,
                            customer_name=f"{customer.resolved_first_name} {customer.resolved_last_name}".strip(),
                            phone=customer.phone or "",
                            favorite_location=customer.favorite_location or "",
                            order_count=customer.int_order_count,
                            lifetime_spend=customer.float_lifetime_spend,
                            last_seen_at=customer.last_visit or customer.leafnet_updated_at or "",
                        )
                    continue

                # Case 2: Email is present but invalid format
                if not customer.has_valid_email:
                    skipped_invalid_email += 1
                    continue

                # Case 3: Goal 3 — Check if this customer was previously a phone-only account!
                if cust_id:
                    prior_phone_only = self.db.get_phone_only_customer(cust_id)
                    if prior_phone_only:
                        existing_emails_captured += 1
                        # Infer employee from latest order if available
                        latest_order = self.db.get_latest_order_for_customer(cust_id)
                        emp_id = latest_order.get("cashier_id", "") if latest_order else ""
                        emp_name = latest_order.get("cashier_name", "Staff (Inferred from Sync)") if latest_order else "Staff (Pending Leafnet Log)"
                        self.db.record_employee_email_change(
                            customer_id=cust_id,
                            old_email="",
                            new_email=customer.clean_email,
                            employee_id=emp_id,
                            employee_name=emp_name,
                            location=customer.favorite_location or prior_phone_only.get("favorite_location", ""),
                            action_type="email_add_existing",
                            timestamp=customer.leafnet_updated_at,
                        )
                        self.db.remove_phone_only_customer(cust_id)

                # Check opt-out status
                opt_out = self.is_opted_out(customer.opt_status)
                if opt_out:
                    skipped_opted_out += 1

                # Build Omnisend contact payload
                payload = self.build_omnisend_contact(customer)

                # Upsert to Omnisend
                try:
                    await self.omnisend.upsert_contact(payload)
                    synced_count += 1

                    # Goal 6: Check Welcome & Loyalty Milestone journeys for subscribed contacts
                    if cust_id and not opt_out:
                        prior_state = self.db.get_customer_sync_state(cust_id)
                        prev_points = float(prior_state["last_points_balance"]) if prior_state else 0.0
                        prev_milestone = float(prior_state["highest_milestone_notified"]) if prior_state else 0.0
                        welcome_sent = bool(prior_state["welcome_sent"]) if prior_state else False

                        send_loyalty_events = settings.loyalty_enabled and not settings.contacts_only
                        if send_loyalty_events:
                            # Trigger Welcome Event if new loyalty signup and not yet welcomed
                            if not welcome_sent and "new-loyalty-signup" in (payload.tags or []):
                                try:
                                    welcome_event = OmnisendEventPayload(
                                        eventName="New Loyalty Signup",
                                        email=customer.clean_email,
                                        phone=self.clean_phone_number(customer.phone) or None,
                                        eventID=f"welcome-signup-{cust_id}",
                                        properties={
                                            "leafnet_customer_id": cust_id,
                                            "first_name": customer.resolved_first_name,
                                            "home_store": customer.favorite_location or "",
                                            "points_balance": customer.float_points,
                                            "signup_date": customer.leafnet_created_at or customer.first_visit or "",
                                        },
                                    )
                                    await self.omnisend.trigger_event(welcome_event)
                                    welcome_sent = True
                                    new_signups_triggered += 1
                                except Exception as we:
                                    logger.warning(f"Failed to trigger welcome event for {customer.clean_email}: {we}")

                            # Check & trigger loyalty milestones (100 pts, 200 pts, etc.)
                            baseline = max(prev_points, prev_milestone)
                            crossed = await self.loyalty.check_and_trigger_milestones(
                                email=customer.clean_email,
                                phone=self.clean_phone_number(customer.phone) or None,
                                points=customer.float_points,
                                previous_points=baseline,
                            )
                            if crossed:
                                milestones_triggered += len(crossed)
                                prev_milestone = max([m["threshold"] for m in crossed])
                        else:
                            # Remember the tier already reached so turning loyalty on later
                            # does not email the whole imported list.
                            prev_milestone = max(
                                prev_milestone,
                                LoyaltyService.highest_reached_threshold(customer.float_points),
                            )
                            welcome_sent = True

                        self.db.upsert_customer_sync_state(
                            leafnet_customer_id=cust_id,
                            email=customer.clean_email,
                            phone=self.clean_phone_number(customer.phone),
                            points_balance=customer.float_points,
                            highest_milestone_notified=prev_milestone,
                            welcome_sent=welcome_sent,
                        )

                except Exception as ex:
                    failed_records += 1
                    err_msg = f"Failed to sync customer {customer.leafnet_customer_id} ({customer.clean_email}): {ex}"
                    logger.error(err_msg)
                    if len(errors) < 25:
                        errors.append(err_msg)

            # Update cursor if new updates were seen
            if latest_updated_at:
                self.db.set_cursor("last_leafnet_updated_at", latest_updated_at)

            success = failed_records == 0 or (synced_count > 0 and failed_records < total_fetched * 0.1)

            self.db.record_sync_finish(
                sync_id=sync_id,
                total_fetched=total_fetched,
                synced_to_omnisend=synced_count,
                skipped_no_email=skipped_no_email,
                skipped_invalid_email=skipped_invalid_email,
                skipped_opted_out=skipped_opted_out,
                failed_records=failed_records,
                errors=errors,
                success=success,
            )

            logger.info(
                f"Sync completed! Fetched: {total_fetched}, Synced: {synced_count}, "
                f"New Signups: {new_signups_triggered}, Milestones: {milestones_triggered}, "
                f"Existing Emails Captured: {existing_emails_captured}, "
                f"Skipped No Email: {skipped_no_email}, Failed: {failed_records}"
            )

            return SyncRunSummary(
                id=sync_id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                sync_type=sync_type,
                total_fetched=total_fetched,
                synced_to_omnisend=synced_count,
                skipped_no_email=skipped_no_email,
                skipped_invalid_email=skipped_invalid_email,
                skipped_opted_out=skipped_opted_out,
                new_signups_triggered=new_signups_triggered,
                milestones_triggered=milestones_triggered,
                existing_emails_captured=existing_emails_captured,
                failed_records=failed_records,
                errors=errors,
                success=success,
            )

        except Exception as e:
            logger.exception(f"Sync failed with critical error: {e}")
            errors.append(str(e))
            self.db.record_sync_finish(
                sync_id=sync_id,
                total_fetched=total_fetched,
                synced_to_omnisend=synced_count,
                skipped_no_email=skipped_no_email,
                skipped_invalid_email=skipped_invalid_email,
                skipped_opted_out=skipped_opted_out,
                failed_records=failed_records,
                errors=errors,
                success=False,
            )
            return SyncRunSummary(
                id=sync_id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                sync_type=sync_type,
                total_fetched=total_fetched,
                synced_to_omnisend=synced_count,
                skipped_no_email=skipped_no_email,
                skipped_invalid_email=skipped_invalid_email,
                skipped_opted_out=skipped_opted_out,
                new_signups_triggered=new_signups_triggered,
                milestones_triggered=milestones_triggered,
                existing_emails_captured=existing_emails_captured,
                failed_records=failed_records,
                errors=errors,
                success=False,
            )
