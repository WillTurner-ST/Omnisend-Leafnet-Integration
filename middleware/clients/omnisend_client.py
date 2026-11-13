import logging
from typing import Optional, Dict, Any
import httpx
from middleware.config import settings
from middleware.models.omnisend import (
    OmnisendContactPayload,
    OmnisendOrderPayload,
    OmnisendEventPayload,
)

logger = logging.getLogger("middleware.omnisend_client")

CURRENT_API_BASE_URL = "https://api.omnisend.com/api"


def normalize_omnisend_base_url(url: Optional[str]) -> str:
    """Map retired /v3 and /v5 bases onto the current /api base."""
    cleaned = (url or CURRENT_API_BASE_URL).rstrip("/")
    if cleaned.endswith("/v3") or cleaned.endswith("/v5"):
        logger.warning(
            "Omnisend base URL %s is a retired path. Using %s with Omnisend-Version %s.",
            cleaned,
            CURRENT_API_BASE_URL,
            settings.omnisend_api_version,
        )
        return CURRENT_API_BASE_URL
    return cleaned


class OmnisendClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or settings.omnisend_api_key
        self.base_url = normalize_omnisend_base_url(base_url or settings.omnisend_base_url)

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Omnisend-API-Key {self.api_key}",
            "Omnisend-Version": settings.omnisend_api_version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def upsert_contact(self, contact: OmnisendContactPayload) -> Dict[str, Any]:
        """
        Creates or updates a contact in Omnisend with custom properties and tags.
        Endpoint: POST /v3/contacts
        """
        url = f"{self.base_url}/contacts"
        payload = contact.model_dump(exclude_none=True)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload)
                # If contact already exists or updated, Omnisend returns 200 OK or 201 Created
                if response.status_code in (200, 201):
                    return response.json()
                elif response.status_code == 409:
                    # Conflict / already exists, attempt patch if needed or return status
                    logger.warning(f"Omnisend contact conflict (409): {response.text}")
                    return response.json() if response.text else {"status": "exists"}
                else:
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Omnisend Contact HTTP Error {e.response.status_code}: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Omnisend Contact Request Failed: {e}")
                raise

    async def create_order(self, order: OmnisendOrderPayload) -> Dict[str, Any]:
        """
        Posts a completed retail purchase to Omnisend Orders API.
        Endpoint: POST /v3/orders
        """
        url = f"{self.base_url}/orders"
        payload = order.model_dump(exclude_none=True)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Omnisend Order HTTP Error {e.response.status_code}: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Omnisend Order Request Failed: {e}")
                raise

    async def trigger_event(self, event: OmnisendEventPayload) -> Dict[str, Any]:
        """
        Triggers a custom event in Omnisend (e.g. for instant post-purchase journeys or loyalty milestones).
        Endpoint: POST /v3/events
        """
        url = f"{self.base_url}/events"
        payload = event.model_dump(exclude_none=True)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                return response.json() if response.text else {"status": "success"}
            except httpx.HTTPStatusError as e:
                logger.error(f"Omnisend Event HTTP Error {e.response.status_code}: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Omnisend Event Request Failed: {e}")
                raise
