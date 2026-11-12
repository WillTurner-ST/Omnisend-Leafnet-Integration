import logging
from typing import Optional, Dict, Any, Union
import httpx
from middleware.config import settings
from middleware.models.leafnet import (
    LoyaltyLookupResponse,
    LoyaltyRedeemResponse,
)

logger = logging.getLogger("middleware.leafnet_client")


class LeafnetClient:
    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        folder_name: Optional[str] = None,
    ):
        self.api_url = api_url or settings.leafnet_api_url
        self.api_key = api_key or settings.leafnet_api_key
        self.folder_name = folder_name or settings.leafnet_folder_name

    def _base_payload(self, command: str) -> Dict[str, Any]:
        return {
            "api_key": self.api_key,
            "folder_name": self.folder_name,
            "command": command,
        }

    async def _post_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                data = response.json()
                if data.get("status") != "success":
                    logger.warning(f"Leafnet non-success response: {data}")
                return data
            except httpx.HTTPStatusError as e:
                logger.error(f"Leafnet HTTP Error {e.response.status_code}: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Leafnet Request Failed: {e}")
                raise

    async def loyalty_lookup(self, phone: str, get_history: bool = False) -> LoyaltyLookupResponse:
        """Looks up loyalty points balance and optional ledger history by phone number."""
        payload = self._base_payload("loyalty_lookup")
        payload["phone"] = phone
        if get_history:
            payload["get_history"] = True

        data = await self._post_command(payload)
        resp_data = data.get("data", {})
        return LoyaltyLookupResponse(
            phone=resp_data.get("phone", phone),
            match_found=bool(resp_data.get("match_found", False)),
            email=resp_data.get("email"),
            first_name=resp_data.get("first_name") or resp_data.get("firstname"),
            last_name=resp_data.get("last_name") or resp_data.get("lastname"),
            points=float(resp_data.get("points", 0.0)),
            history=resp_data.get("history"),
            ts=resp_data.get("ts"),
        )

    async def loyalty_redeem(
        self,
        phone: str,
        points: float,
        description: str,
        order_id: Union[str, int],
        discount_id: Optional[str] = None,
        location_code: Optional[str] = None,
    ) -> LoyaltyRedeemResponse:
        """Deducts loyalty points in Leafnet for coupon/milestone redemption at checkout."""
        payload = self._base_payload("loyalty_redeem")
        payload["phone"] = phone
        payload["points"] = points
        payload["description"] = description
        payload["order_id"] = order_id
        if discount_id:
            payload["discount_id"] = discount_id
        if location_code:
            payload["location_code"] = location_code

        data = await self._post_command(payload)
        resp_data = data.get("data", {})
        return LoyaltyRedeemResponse(
            redeemed=bool(resp_data.get("redeemed", False)),
            phone=resp_data.get("phone", phone),
            points_deducted=float(resp_data.get("points_deducted", points)),
            points_remaining=float(resp_data.get("points_remaining", 0.0)),
            ts=resp_data.get("ts"),
        )

    async def loyalty_adjust(
        self,
        phone: str,
        points: float,
        description: str = "Adjustment via middleware",
    ) -> Dict[str, Any]:
        """Manually adds or adjusts loyalty points for a customer."""
        payload = self._base_payload("loyalty_adjust")
        payload["phone"] = phone
        payload["points"] = points
        payload["description"] = description
        return await self._post_command(payload)

    async def loyalty_create(
        self,
        phone: str,
        first_name: str,
        last_name: str,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new loyalty profile in Leafnet."""
        payload = self._base_payload("loyalty_create")
        payload["phone"] = phone
        payload["first_name"] = first_name
        payload["last_name"] = last_name
        if email:
            payload["email"] = email
        return await self._post_command(payload)

    async def customer_history(self, customer_id: Union[str, int]) -> Dict[str, Any]:
        """Fetches full customer profile, macro category stats, and orders list for verification."""
        payload = self._base_payload("customer_history")
        payload["customer_id"] = str(customer_id)
        return await self._post_command(payload)

    async def customer_search(self, search_term: str) -> Dict[str, Any]:
        """Searches customer by name (3 or more chars)."""
        payload = self._base_payload("customer_search")
        payload["Search"] = search_term
        return await self._post_command(payload)

    async def get_categories(self, full_details: bool = True) -> Dict[str, Any]:
        """Fetches catalog categories mapping."""
        payload = self._base_payload("get_categories")
        payload["full_details"] = full_details
        return await self._post_command(payload)

    async def run_report(
        self,
        report: str,
        from_date: str,
        to_date: Optional[str] = None,
        location_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a Leafnet report command (e.g. 'Top Customers by Date Range',
        'Order List', 'Sales by Category', 'Payments by Order Staff').
        """
        payload = self._base_payload("run_report")
        payload["report"] = report
        payload["from_date"] = from_date
        if to_date:
            payload["to_date"] = to_date
        if location_code:
            payload["location_code"] = location_code
        return await self._post_command(payload)
