import logging
from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any
from middleware.models.leafnet import (
    LoyaltyLookupRequest,
    LoyaltyLookupResponse,
    LoyaltyRedeemRequest,
    LoyaltyRedeemResponse,
    LoyaltyAdjustRequest,
    LoyaltyCreateRequest,
)
from middleware.services.loyalty_service import LoyaltyService
from middleware.clients.leafnet_client import LeafnetClient

logger = logging.getLogger("middleware.routes_loyalty")
router = APIRouter(prefix="/api/loyalty", tags=["Loyalty"])

loyalty_service = LoyaltyService()
leafnet_client = LeafnetClient()


@router.post("/lookup", response_model=LoyaltyLookupResponse, summary="Lookup Loyalty Balance and Ledger")
async def lookup_loyalty(payload: LoyaltyLookupRequest):
    """Looks up current customer points balance and optional transaction history by phone number."""
    try:
        return await loyalty_service.get_loyalty_balance(
            phone=payload.phone,
            get_history=bool(payload.get_history),
        )
    except Exception as e:
        logger.exception(f"Loyalty lookup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loyalty lookup error: {str(e)}",
        )


@router.post("/redeem", response_model=LoyaltyRedeemResponse, summary="Redeem Points for Milestone Reward")
async def redeem_points(payload: LoyaltyRedeemRequest):
    """
    Deducts points in Leafnet when a customer redeems a loyalty reward discount at POS checkout.
    Emits a redemption event in Omnisend if customer email is on file.
    """
    try:
        return await loyalty_service.redeem_reward(
            phone=payload.phone,
            points=payload.points,
            description=payload.description,
            order_id=str(payload.order_id),
            discount_id=payload.discount_id,
            location_code=payload.location_code,
        )
    except Exception as e:
        logger.exception(f"Loyalty redeem error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loyalty redeem error: {str(e)}",
        )


@router.post("/adjust", summary="Manually Adjust Loyalty Points")
async def adjust_points(payload: LoyaltyAdjustRequest) -> Dict[str, Any]:
    """Manually credits or debits points for a customer."""
    try:
        return await leafnet_client.loyalty_adjust(
            phone=payload.phone,
            points=payload.points,
            description=payload.description or "Adjustment via middleware",
        )
    except Exception as e:
        logger.exception(f"Loyalty adjust error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loyalty adjust error: {str(e)}",
        )


@router.post("/create", summary="Create New Loyalty Profile")
async def create_loyalty_account(payload: LoyaltyCreateRequest) -> Dict[str, Any]:
    """Creates a new loyalty profile in Leafnet."""
    try:
        return await leafnet_client.loyalty_create(
            phone=payload.phone,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
        )
    except Exception as e:
        logger.exception(f"Loyalty create error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loyalty create error: {str(e)}",
        )
