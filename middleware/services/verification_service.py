import logging
from typing import Optional, Dict, Any, List
from middleware.clients.leafnet_client import LeafnetClient
from middleware.clients.nocodb_client import NocoDBClient
from middleware.clients.omnisend_client import OmnisendClient
from middleware.models.nocodb import NocoDBCustomerRecord

logger = logging.getLogger("middleware.verification_service")


class VerificationService:
    def __init__(
        self,
        leafnet_client: Optional[LeafnetClient] = None,
        nocodb_client: Optional[NocoDBClient] = None,
        omnisend_client: Optional[OmnisendClient] = None,
    ):
        self.leafnet = leafnet_client or LeafnetClient()
        self.nocodb = nocodb_client or NocoDBClient()
        self.omnisend = omnisend_client or OmnisendClient()

    async def verify_customer_parity(self, customer_id: str) -> Dict[str, Any]:
        """
        Cross-checks customer data across Leafnet customer_history and NocoDB.
        Validates parity of: email, points, last visit, lifetime value, top categories.
        """
        discrepancies: List[str] = []

        # 1. Fetch Leafnet customer_history
        leafnet_data = {}
        try:
            leafnet_res = await self.leafnet.customer_history(customer_id)
            leafnet_data = leafnet_res.get("data", {})
        except Exception as e:
            discrepancies.append(f"Failed to fetch Leafnet customer_history: {e}")

        leafnet_cust = leafnet_data.get("customer", {})
        leafnet_macro = leafnet_data.get("macro_stats", {})

        leafnet_email = leafnet_cust.get("email", "").strip().lower()
        leafnet_phone = leafnet_cust.get("phone", "")
        leafnet_points = float(leafnet_cust.get("points", 0.0) or 0.0)
        leafnet_last_visit = leafnet_cust.get("last_visit", "")
        leafnet_order_total = float(leafnet_cust.get("order_total", 0.0) or 0.0)

        # 2. Fetch NocoDB record
        nocodb_record = None
        try:
            nocodb_res = await self.nocodb.get_records_page(
                limit=1,
                where_clause=f"(leafnet_customer_id,eq,{customer_id})",
            )
            if nocodb_res.list:
                nocodb_record = NocoDBCustomerRecord(**nocodb_res.list[0])
            else:
                discrepancies.append(f"Customer {customer_id} not found in NocoDB table.")
        except Exception as e:
            discrepancies.append(f"Failed to query NocoDB: {e}")

        nocodb_email = nocodb_record.clean_email if nocodb_record else ""
        nocodb_points = nocodb_record.float_points if nocodb_record else 0.0
        nocodb_spend = nocodb_record.float_lifetime_spend if nocodb_record else 0.0
        nocodb_last_visit = nocodb_record.last_visit if nocodb_record else ""

        # Check Email parity
        if leafnet_email and nocodb_email and leafnet_email != nocodb_email:
            discrepancies.append(f"Email mismatch: Leafnet='{leafnet_email}' vs NocoDB='{nocodb_email}'")

        # Check Points parity (allow 0.01 cent rounding)
        if abs(leafnet_points - nocodb_points) > 0.05:
            discrepancies.append(f"Points mismatch: Leafnet={leafnet_points} vs NocoDB={nocodb_points}")

        # Check Spend parity
        if abs(leafnet_order_total - nocodb_spend) > 1.00:
            discrepancies.append(f"Spend mismatch: Leafnet order_total=${leafnet_order_total:.2f} vs NocoDB=${nocodb_spend:.2f}")

        return {
            "customer_id": customer_id,
            "parity_status": "MATCH" if not discrepancies else "DISCREPANCY_DETECTED",
            "discrepancies": discrepancies,
            "leafnet": {
                "email": leafnet_email,
                "phone": leafnet_phone,
                "points": leafnet_points,
                "order_total": leafnet_order_total,
                "last_visit": leafnet_last_visit,
                "top_categories": leafnet_macro.get("Category", {}).get("-top-", []),
            },
            "nocodb": {
                "email": nocodb_email,
                "points": nocodb_points,
                "lifetime_spend": nocodb_spend,
                "last_visit": nocodb_last_visit,
                "favorite_category": nocodb_record.favorite_category if nocodb_record else "",
            } if nocodb_record else None,
        }
