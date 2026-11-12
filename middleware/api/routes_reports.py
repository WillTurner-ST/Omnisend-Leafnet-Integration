from fastapi import APIRouter
from typing import List
from middleware.models.internal import PhoneOnlyStoreSummary, EmployeeAcquisitionSummary
from middleware.services.attribution_service import AttributionService

router = APIRouter(prefix="/api/reports", tags=["Reports"])
attribution_service = AttributionService()


@router.get("/phone-only", response_model=List[PhoneOnlyStoreSummary], summary="In-Store Phone-Only Audit")
def get_phone_only_report():
    """
    Returns store-by-store breakdown of customers with phone numbers but missing emails.
    Enables store managers and budtenders to prioritize email collection at the register.
    """
    return attribution_service.get_phone_only_store_report()


@router.get("/staff-email-acquisitions", response_model=List[EmployeeAcquisitionSummary], summary="Staff Email Collection Leaderboard")
def get_staff_email_acquisitions():
    """
    Returns staff performance report showing how many accounts gained an email through each employee.
    Used for staff incentives and recognition.
    """
    return attribution_service.get_employee_report()
