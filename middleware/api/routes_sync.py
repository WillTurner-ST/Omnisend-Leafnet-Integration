import logging
from fastapi import APIRouter, Query, HTTPException, status
from typing import Dict, Any, List
from middleware.services.contact_sync_service import ContactSyncService
from middleware.database.db import Database
from middleware.config import settings

logger = logging.getLogger("middleware.routes_sync")
router = APIRouter(prefix="/api/sync", tags=["Sync"])

sync_service = ContactSyncService()
db = Database(settings.db_path)


@router.post("/run", summary="Trigger Customer Sync from NocoDB to Omnisend")
async def trigger_sync(
    full: bool = Query(False, description="Whether to run full sync instead of incremental")
) -> Dict[str, Any]:
    """
    Manually triggers customer synchronization from NocoDB table to Omnisend contacts.
    - full=False (default): only pulls records modified since last sync cursor.
    - full=True: pulls all records.
    """
    try:
        summary = await sync_service.run_sync(full_sync=full)
        return summary.model_dump()
    except Exception as e:
        logger.exception(f"Sync execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync execution error: {str(e)}",
        )


@router.get("/history", summary="Get Recent Sync Runs History")
async def get_sync_history(limit: int = Query(10, ge=1, le=100)) -> List[Dict[str, Any]]:
    """Returns past sync execution summaries from the database."""
    return db.get_latest_sync_runs(limit=limit)


@router.get("/cursor", summary="Get Current Sync Cursor")
async def get_cursor() -> Dict[str, Any]:
    """Returns current timestamp cursor used for incremental sync."""
    cursor_val = db.get_cursor("last_leafnet_updated_at")
    return {"cursor_key": "last_leafnet_updated_at", "value": cursor_val}


@router.post("/cursor", summary="Reset or Update Sync Cursor")
async def set_cursor(payload: Dict[str, str]) -> Dict[str, Any]:
    """Allows updating or clearing the sync cursor timestamp."""
    val = payload.get("value")
    if val is None:
        raise HTTPException(status_code=400, detail="Missing 'value' in payload")
    db.set_cursor("last_leafnet_updated_at", val)
    return {"status": "updated", "value": val}
