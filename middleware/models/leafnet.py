from typing import Optional, Any, List, Union
from pydantic import BaseModel, Field


class LeafnetMacro(BaseModel):
    type: str
    value: str


class LeafnetDiscount(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    subtotal: Optional[float] = None
    amount: Optional[float] = None


class LeafnetOrderItem(BaseModel):
    item_id: Union[str, int]
    name: str
    qty: Union[int, float] = 1
    base_cost: Optional[Union[float, str]] = None
    unit_cost: Optional[Union[float, str]] = None
    cost: Optional[Union[float, str]] = None
    barcode: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    category_id: Optional[Union[str, int]] = None
    category_name: Optional[str] = None
    macros: Optional[List[LeafnetMacro]] = None
    discount: Optional[Union[LeafnetDiscount, dict]] = None

    model_config = {"extra": "allow"}

    @property
    def price_as_float(self) -> float:
        """Derives float unit price from unit_cost, base_cost, or cost."""
        for candidate in [self.unit_cost, self.base_cost, self.cost]:
            if candidate is not None:
                try:
                    cleaned = str(candidate).replace("$", "").replace(",", "").strip()
                    val = float(cleaned)
                    qty = float(self.qty) if self.qty else 1.0
                    # If cost is total for the line, divide by qty
                    if candidate is self.cost and qty > 1 and not self.unit_cost:
                        return round(val / qty, 2)
                    return val
                except (ValueError, TypeError):
                    continue
        return 0.0

    @property
    def resolved_category(self) -> str:
        """Resolves category name from category_name or macros list."""
        if self.category_name and self.category_name.strip():
            return self.category_name.strip()
        if self.macros:
            for m in self.macros:
                if m.type.lower() == "category":
                    return m.value.strip()
        return "General"


class LeafnetOrderWebhookPayload(BaseModel):
    """
    Represents the order-completion webhook payload fired by Leafnet.
    Flexible enough to handle both direct webhook formats and customer_history order format.
    """
    order_id: Optional[Union[str, int]] = Field(default=None, alias="Order Id")
    customer_id: Optional[Union[str, int]] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created: Optional[str] = Field(default=None, alias="Created")
    location: Optional[str] = Field(default=None, alias="Location")
    subtotal: Optional[Union[float, str]] = Field(default=0.0, alias="Subtotal")
    discounts: Optional[Union[float, str]] = Field(default=0.0, alias="Discounts")
    tax: Optional[Union[float, str]] = Field(default=0.0, alias="Tax and Fees")
    total: Optional[Union[float, str]] = Field(default=0.0, alias="Total")
    items: Optional[List[LeafnetOrderItem]] = Field(default=None, alias="Contents")
    account_id: Optional[str] = None
    account_name: Optional[str] = None

    model_config = {"extra": "allow", "populate_by_name": True}

    @property
    def clean_order_id(self) -> str:
        raw = self.order_id or ""
        return str(raw).replace("#", "").strip()

    @property
    def float_total(self) -> float:
        try:
            return float(str(self.total).replace("$", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return 0.0

    @property
    def float_subtotal(self) -> float:
        try:
            return float(str(self.subtotal).replace("$", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return 0.0

    @property
    def float_discounts(self) -> float:
        try:
            return abs(float(str(self.discounts).replace("$", "").replace(",", "").strip()))
        except (ValueError, TypeError):
            return 0.0

    @property
    def float_tax(self) -> float:
        try:
            return float(str(self.tax).replace("$", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return 0.0

    @property
    def total_cents(self) -> int:
        return int(round(self.float_total * 100))

    @property
    def subtotal_cents(self) -> int:
        return int(round(self.float_subtotal * 100))

    @property
    def discount_cents(self) -> int:
        return int(round(self.float_discounts * 100))

    @property
    def tax_cents(self) -> int:
        return int(round(self.float_tax * 100))

    @property
    def categories(self) -> List[str]:
        cat_set = []
        if self.items:
            for item in self.items:
                cat = item.resolved_category
                if cat and cat not in cat_set:
                    cat_set.append(cat)
        return cat_set

    @property
    def staff_account_id(self) -> str:
        if self.account_id:
            return str(self.account_id)
        if self.items:
            for item in self.items:
                if item.account_id:
                    return str(item.account_id)
        return ""

    @property
    def staff_account_name(self) -> str:
        if self.account_name:
            return str(self.account_name)
        if self.items:
            for item in self.items:
                if item.account_name:
                    return str(item.account_name)
        return ""


# ============================================================================
# Loyalty Models
# ============================================================================

class LoyaltyLookupRequest(BaseModel):
    phone: str
    get_history: Optional[bool] = False


class LoyaltyLedgerEntry(BaseModel):
    datetime: Optional[str] = None
    order_id: Optional[str] = None
    points: Optional[Union[float, str]] = None
    item_name: Optional[str] = None
    points_action: Optional[str] = None


class LoyaltyLookupResponse(BaseModel):
    phone: str
    match_found: bool
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    points: float = 0.0
    history: Optional[List[LoyaltyLedgerEntry]] = None
    ts: Optional[int] = None


class LoyaltyRedeemRequest(BaseModel):
    phone: str
    points: float
    description: str
    order_id: Union[str, int]
    discount_id: Optional[str] = None
    location_code: Optional[str] = None


class LoyaltyRedeemResponse(BaseModel):
    redeemed: bool
    phone: str
    points_deducted: float
    points_remaining: float
    ts: Optional[int] = None


class LoyaltyAdjustRequest(BaseModel):
    phone: str
    points: float
    description: Optional[str] = "Adjustment via middleware"


class LoyaltyCreateRequest(BaseModel):
    phone: str
    first_name: str
    last_name: str
    email: Optional[str] = None


# ============================================================================
# Employee Email Attribution Model
# ============================================================================

class CustomerEmailChangePayload(BaseModel):
    customer_id: Union[str, int]
    old_email: Optional[str] = None
    new_email: str
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    timestamp: Optional[str] = None
    location: Optional[str] = None
