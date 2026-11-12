import logging
from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any
from middleware.services.verification_service import VerificationService

logger = logging.getLogger("middleware.routes_verify")
router = APIRouter(prefix="/api/verify", tags=["Verification"])
verification_service = VerificationService()


@router.get("/customer/{customer_id}", summary="Verify Customer Parity (Leafnet vs NocoDB)")
async def verify_customer(customer_id: str) -> Dict[str, Any]:
    """
    Performs Step 9 Parity Verification:
    Compares customer data between Leafnet customer_history API and NocoDB table row.
    Checks parity of: email, points balance, last visit, lifetime spend, and top categories.
    """
    try:
        result = await verification_service.verify_customer_parity(customer_id)
        return result
    except Exception as e:
        logger.exception(f"Verification check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification check error: {str(e)}",
        )
