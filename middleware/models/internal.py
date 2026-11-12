from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class SyncRunSummary(BaseModel):
    id: Optional[int] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    sync_type: str = "incremental"  # 'full' or 'incremental'
    total_fetched: int = 0
    synced_to_omnisend: int = 0
    skipped_no_email: int = 0
    skipped_invalid_email: int = 0
    skipped_opted_out: int = 0
    new_signups_triggered: int = 0
    milestones_triggered: int = 0
    existing_emails_captured: int = 0
    failed_records: int = 0
    errors: List[str] = Field(default_factory=list)
    success: bool = True


class PhoneOnlyStoreSummary(BaseModel):
    store_location: str
    phone_only_count: int
    total_customers: int
    email_capture_rate_percent: float


class EmployeeAcquisitionSummary(BaseModel):
    employee_id: str
    employee_name: str
    emails_collected_count: int
    existing_account_emails: int = 0
    new_signup_emails: int = 0
    sales_count: int = 0
