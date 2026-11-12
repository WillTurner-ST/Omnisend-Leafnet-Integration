import logging
from typing import Optional, List, Dict, Any
from middleware.config import settings
from middleware.database.db import Database
from middleware.models.leafnet import CustomerEmailChangePayload
from middleware.models.internal import PhoneOnlyStoreSummary, EmployeeAcquisitionSummary

logger = logging.getLogger("middleware.attribution_service")


class AttributionService:
    def __init__(self, database: Optional[Database] = None):
        self.db = database or Database(settings.db_path)

    def log_customer_email_change(self, change: CustomerEmailChangePayload) -> Dict[str, Any]:
        """
        Records when a staff member adds or updates an email for an account (Goal 3).
        Supports both Leafnet's customer-updated webhook and manual POS email change feed.
        """
        cust_id = str(change.customer_id)
        prior_phone_only = self.db.get_phone_only_customer(cust_id)
        action = "email_add_existing" if (not change.old_email or prior_phone_only) else "email_change"

        self.db.record_employee_email_change(
            customer_id=cust_id,
            old_email=change.old_email,
            new_email=change.new_email,
            employee_id=change.employee_id,
            employee_name=change.employee_name,
            location=change.location,
            action_type=action,
            timestamp=change.timestamp,
        )

        # If this customer was in phone-only list, remove them now
        self.db.remove_phone_only_customer(cust_id)

        return {
            "status": "success",
            "customer_id": change.customer_id,
            "employee_id": change.employee_id,
            "employee_name": change.employee_name,
            "action": action,
        }

    def get_employee_report(self) -> List[EmployeeAcquisitionSummary]:
        """Returns staff performance leaderboard for email collections (Goal 3)."""
        rows = self.db.get_employee_email_acquisitions()
        return [
            EmployeeAcquisitionSummary(
                employee_id=r["employee_id"],
                employee_name=r["employee_name"],
                emails_collected_count=r["emails_collected_count"],
                existing_account_emails=r.get("existing_account_emails") or 0,
                new_signup_emails=r.get("new_signup_emails") or 0,
            )
            for r in rows
        ]

    def get_phone_only_store_report(self) -> List[PhoneOnlyStoreSummary]:
        """Returns phone-only metrics per store location to identify email capture opportunities."""
        rows = self.db.get_phone_only_by_store()
        summaries = []
        for r in rows:
            phone_only = r["phone_only_count"]
            summaries.append(
                PhoneOnlyStoreSummary(
                    store_location=r["store_location"],
                    phone_only_count=phone_only,
                    total_customers=phone_only,
                    email_capture_rate_percent=0.0,
                )
            )
        return summaries
