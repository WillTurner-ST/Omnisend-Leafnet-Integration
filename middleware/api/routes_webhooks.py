import logging
from fastapi import APIRouter, Header, HTTPException, status, Depends
from typing import Optional, Dict, Any
from middleware.config import settings
from middleware.models.leafnet import LeafnetOrderWebhookPayload, CustomerEmailChangePayload
from middleware.services.webhook_service import WebhookService
from middleware.services.attribution_service import AttributionService

logger = logging.getLogger("middleware.routes_webhooks")
router = APIRouter(prefix="/webhooks/leafnet", tags=["Webhooks"])

webhook_service = WebhookService()
attribution_service = AttributionService()


def verify_webhook_token(x_webhook_secret: Optional[str] = Header(None)):
    if settings.webhook_secret and x_webhook_secret != settings.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook secret header",
        )


@router.post("/order-completed", summary="Leafnet Order Completion Webhook")
async def handle_order_completed(
    payload: LeafnetOrderWebhookPayload,
    _: None = Depends(verify_webhook_token),
) -> Dict[str, Any]:
    """
    Receives real-time order-completion webhook from Leafnet POS:
    - Normalizes line items & extracts categories
    - Converts prices to integer cents
    - Sends placed order to Omnisend Orders API
    - Triggers 'Retail Purchase Completed' event in Omnisend for post-purchase automation
    - Updates contact metrics in real-time
    - Handles deduplication and staff attribution
    """
    try:
        result = await webhook_service.process_order_completed(payload)
        return result
    except Exception as e:
        logger.exception(f"Error processing order completed webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing error: {str(e)}",
        )


@router.post("/customer-updated", summary="Leafnet Customer Updated / Email Changed")
async def handle_customer_updated(
    payload: CustomerEmailChangePayload,
    _: None = Depends(verify_webhook_token),
) -> Dict[str, Any]:
    """
    Receives customer update events (e.g. employee adding email to existing account).
    Logs staff attribution for incentive tracking and removes customer from phone-only list.
    """
    try:
        result = attribution_service.log_customer_email_change(payload)
        return result
    except Exception as e:
        logger.exception(f"Error logging customer update: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing customer update: {str(e)}",
        )
