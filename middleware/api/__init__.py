from middleware.api.routes_webhooks import router as webhooks_router
from middleware.api.routes_sync import router as sync_router
from middleware.api.routes_loyalty import router as loyalty_router
from middleware.api.routes_reports import router as reports_router
from middleware.api.routes_verify import router as verify_router

__all__ = [
    "webhooks_router",
    "sync_router",
    "loyalty_router",
    "reports_router",
    "verify_router",
]
