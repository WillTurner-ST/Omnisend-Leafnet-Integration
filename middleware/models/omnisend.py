from typing import Optional, Any, List, Dict
from pydantic import BaseModel, Field


class OmnisendChannelStatus(BaseModel):
    status: str = "subscribed"  # 'subscribed', 'unsubscribed', 'nonSubscribed'
    statusDate: Optional[str] = None


class OmnisendChannels(BaseModel):
    email: Optional[OmnisendChannelStatus] = None
    sms: Optional[OmnisendChannelStatus] = None


class OmnisendIdentifier(BaseModel):
    type: str  # 'email' or 'phone'
    id: str
    channels: Optional[OmnisendChannels] = None
    # Current API sends a welcome when this is omitted and the channel is subscribed.
    sendWelcomeMessage: bool = False


class OmnisendContactCustomProperties(BaseModel):
    leafnet_customer_id: Optional[Any] = None
    phone: Optional[str] = None
    birthday: Optional[str] = None
    home_store: Optional[str] = None
    signup_date: Optional[str] = None
    last_visit_date: Optional[str] = None
    days_since_last_visit: Optional[int] = None
    visit_count: Optional[int] = None
    order_count: Optional[int] = None
    lifetime_value: Optional[float] = None
    average_spend: Optional[float] = None
    points_balance: Optional[float] = None
    top_category: Optional[str] = None
    opt_status: Optional[str] = None

    model_config = {"extra": "allow"}


class OmnisendContactPayload(BaseModel):
    identifiers: List[OmnisendIdentifier]
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    birthdate: Optional[str] = None  # YYYY-MM-DD
    tags: Optional[List[str]] = Field(default_factory=list)
    customProperties: Optional[Dict[str, Any]] = Field(default_factory=dict)


class OmnisendOrderProduct(BaseModel):
    productID: str
    title: str
    quantity: int = 1
    price: int  # in cents!
    sku: Optional[str] = None
    category: Optional[str] = None


class OmnisendOrderPayload(BaseModel):
    orderID: str
    email: Optional[str] = None
    phone: Optional[str] = None
    currency: str = "USD"
    orderSum: int  # in cents!
    subTotalSum: Optional[int] = None  # in cents!
    discountSum: Optional[int] = 0  # in cents!
    taxSum: Optional[int] = 0  # in cents!
    paymentStatus: str = "paid"
    fulfillmentStatus: str = "fulfilled"
    createdAt: str  # ISO-8601
    products: List[OmnisendOrderProduct] = Field(default_factory=list)


class OmnisendEventPayload(BaseModel):
    eventName: str
    email: Optional[str] = None
    phone: Optional[str] = None
    eventID: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
