import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from middleware.config import settings
from middleware.api import (
    webhooks_router,
    sync_router,
    loyalty_router,
    reports_router,
    verify_router,
)
from middleware.services.contact_sync_service import ContactSyncService

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("middleware.main")

scheduler = AsyncIOScheduler()
sync_service = ContactSyncService()


async def scheduled_sync_job():
    logger.info("Executing scheduled daily customer sync (NocoDB -> Omnisend)...")
    try:
        summary = await sync_service.run_sync(full_sync=False)
        logger.info(f"Scheduled sync finished: {summary.synced_to_omnisend} contacts synced.")
    except Exception as e:
        logger.exception(f"Error during scheduled sync: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background scheduler
    if settings.sync_interval_hours > 0:
        logger.info(f"Starting background sync scheduler (every {settings.sync_interval_hours} hours)...")
        scheduler.add_job(
            scheduled_sync_job,
            "interval",
            hours=settings.sync_interval_hours,
            id="daily_customer_sync",
            replace_existing=True,
        )
        scheduler.start()
    yield
    # Shutdown: Stop scheduler
    if scheduler.running:
        logger.info("Shutting down background sync scheduler...")
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Leafnet / NocoDB into Omnisend Middleware",
    description=(
        "Production middleware connecting Leafnet retail POS & NocoDB customer data into Omnisend "
        "for retail email/SMS marketing, automated post-purchase flows, and loyalty milestone rewards."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(webhooks_router)
app.include_router(sync_router)
app.include_router(loyalty_router)
app.include_router(reports_router)
app.include_router(verify_router)


@app.get("/health", tags=["System"])
async def health_check():
    """Returns application health and configuration readiness."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "scheduler_running": scheduler.running,
        "integrations": {
            "omnisend_configured": bool(settings.omnisend_api_key),
            "nocodb_configured": bool(settings.nocodb_api_token and settings.nocodb_table_id),
            "leafnet_configured": bool(settings.leafnet_api_key and settings.leafnet_folder_name),
        },
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "message": "Leafnet / NocoDB into Omnisend Middleware is running.",
        "documentation": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("middleware.main:app", host=settings.host, port=settings.port, reload=True)
