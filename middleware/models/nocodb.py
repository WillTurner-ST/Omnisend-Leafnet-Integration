import json
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict
from pydantic import BaseModel


class NocoDBCustomerRecord(BaseModel):
    """Represents a customer row from the NocoDB Leafnet Customers table (81 columns)."""
    Id: Optional[Any] = None  # NocoDB internal primary key
    leafnet_customer_id: Optional[Any] = None
    key: Optional[str] = None
    email: Optional[str] = ""
    first_name: Optional[str] = ""
    middle_name: Optional[str] = ""
    last_name: Optional[str] = ""
    customer_name: Optional[str] = ""
    phone: Optional[str] = ""
    birth_date: Optional[str] = ""
    favorite_location: Optional[str] = ""
    favorite_location_orders: Optional[Any] = 0
    leafnet_created_at: Optional[str] = ""
    first_visit: Optional[str] = ""
    last_visit: Optional[str] = ""
    days_since_last_visit: Optional[Any] = 0
    visit_count: Optional[Any] = 0
    order_count: Optional[Any] = 0
    lifetime_spend: Optional[Any] = 0.0
    order_total: Optional[Any] = 0.0
    average_order_value: Optional[Any] = 0.0
    average_days_between_visits: Optional[Any] = 0.0
    points: Optional[Any] = 0.0
    favorite_category: Optional[str] = ""
    favorite_category_count: Optional[Any] = 0
    favorite_item: Optional[str] = ""
    favorite_item_id: Optional[Any] = ""
    opt_status: Optional[str] = ""
    signup_source: Optional[str] = ""
    source_version: Optional[str] = ""
    leafnet_updated_at: Optional[str] = ""
    last_synced_at: Optional[str] = ""
    category_stats_json: Optional[Any] = None
    order_history_json: Optional[Any] = None

    # Allow all 81 columns without breaking
    model_config = {"extra": "allow"}

    @property
    def clean_email(self) -> str:
        """Returns lowercase, trimmed email or empty string if absent/invalid."""
        if not self.email:
            return ""
        email_str = str(self.email).strip().lower()
        if "@" in email_str and "." in email_str.split("@")[-1]:
            return email_str
        return ""

    @property
    def has_valid_email(self) -> bool:
        return bool(self.clean_email)

    @property
    def resolved_first_name(self) -> str:
        if self.first_name and self.first_name.strip():
            return self.first_name.strip()
        if self.customer_name and self.customer_name.strip():
            parts = self.customer_name.strip().split()
            return parts[0] if parts else ""
        return ""

    @property
    def resolved_last_name(self) -> str:
        if self.last_name and self.last_name.strip():
            return self.last_name.strip()
        if self.customer_name and self.customer_name.strip():
            parts = self.customer_name.strip().split()
            return " ".join(parts[1:]) if len(parts) > 1 else ""
        return ""

    @property
    def float_lifetime_spend(self) -> float:
        val = self.lifetime_spend if self.lifetime_spend not in (None, "") else self.order_total
        try:
            return float(str(val).replace("$", "").replace(",", "").strip()) if val else 0.0
        except (ValueError, TypeError):
            return 0.0

    @property
    def float_points(self) -> float:
        try:
            return float(self.points) if self.points not in (None, "") else 0.0
        except (ValueError, TypeError):
            return 0.0

    @property
    def int_days_since_last_visit(self) -> int:
        try:
            if self.days_since_last_visit not in (None, ""):
                return int(float(self.days_since_last_visit))
        except (ValueError, TypeError):
            pass
        return 0

    @property
    def int_order_count(self) -> int:
        try:
            return int(float(self.order_count)) if self.order_count not in (None, "") else 0
        except (ValueError, TypeError):
            return 0

    @property
    def int_visit_count(self) -> int:
        try:
            if self.visit_count not in (None, ""):
                return int(float(self.visit_count))
            return self.int_order_count
        except (ValueError, TypeError):
            return 0

    @property
    def float_average_order_value(self) -> float:
        try:
            if self.average_order_value not in (None, ""):
                return float(self.average_order_value)
            if self.int_order_count > 0:
                return round(self.float_lifetime_spend / self.int_order_count, 2)
        except (ValueError, TypeError):
            pass
        return 0.0

    @property
    def float_visit_frequency_days(self) -> float:
        try:
            if self.average_days_between_visits not in (None, ""):
                return float(self.average_days_between_visits)
        except (ValueError, TypeError):
            pass
        return 0.0

    @property
    def resolved_signup_source(self) -> str:
        if self.signup_source and str(self.signup_source).strip():
            return str(self.signup_source).strip()
        return "leafnet_pos"

    @property
    def top_categories_list(self) -> List[str]:
        """Extracts top categories from category_stats_json or favorite_category."""
        cats: List[str] = []
        if self.favorite_category and str(self.favorite_category).strip():
            cats.append(str(self.favorite_category).strip())
        if self.category_stats_json:
            try:
                parsed = (
                    json.loads(self.category_stats_json)
                    if isinstance(self.category_stats_json, str)
                    else self.category_stats_json
                )
                if isinstance(parsed, dict):
                    top = parsed.get("-top-")
                    if isinstance(top, list):
                        for c in top:
                            if c and str(c).strip() not in cats:
                                cats.append(str(c).strip())
                    else:
                        sorted_keys = sorted(
                            [(k, v) for k, v in parsed.items() if k != "-top-" and isinstance(v, (int, float))],
                            key=lambda x: x[1],
                            reverse=True,
                        )
                        for k, _ in sorted_keys[:3]:
                            if k not in cats:
                                cats.append(k)
            except Exception:
                pass
        return cats


class NocoDBPageInfo(BaseModel):
    totalRows: int = 0
    page: int = 1
    pageSize: int = 25
    isFirstPage: bool = True
    isLastPage: bool = True


class NocoDBRecordsResponse(BaseModel):
    list: List[dict] = []
    pageInfo: Optional[NocoDBPageInfo] = None
