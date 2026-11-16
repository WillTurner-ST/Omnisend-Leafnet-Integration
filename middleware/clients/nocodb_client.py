import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import httpx
from middleware.config import settings
from middleware.models.nocodb import NocoDBRecordsResponse

logger = logging.getLogger("middleware.nocodb_client")


def normalize_nocodb_datetime(value: Optional[str]) -> Optional[str]:
    """Convert a NocoDB datetime into `YYYY-MM-DD HH:MM:SS` UTC.

    NocoDB rejects offsets such as `+00:00` in where filters.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed: Optional[datetime] = None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw[:19] if " " in fmt or "T" in fmt else raw[:10], fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def build_updated_since_filter(since_timestamp: Optional[str]) -> Optional[str]:
    """NocoDB DateTime filters require the exactDate sub-operator."""
    if since_timestamp is None or str(since_timestamp).strip() == "":
        return None
    normalized = normalize_nocodb_datetime(since_timestamp)
    if not normalized:
        raise ValueError(f"Unrecognized NocoDB timestamp: {since_timestamp}")
    return f"(leafnet_updated_at,gt,exactDate,{normalized})"


class NocoDBClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        table_id: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.nocodb_api_url).rstrip("/")
        self.api_token = api_token or settings.nocodb_api_token
        self.table_id = table_id or settings.nocodb_table_id

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "xc-token": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def get_records_page(
        self,
        offset: int = 0,
        limit: int = 100,
        where_clause: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> NocoDBRecordsResponse:
        """Fetches a single page of records from NocoDB table."""
        url = f"{self.base_url}/api/v2/tables/{self.table_id}/records"
        params: Dict[str, Any] = {
            "offset": offset,
            "limit": limit,
        }
        if where_clause:
            params["where"] = where_clause
        if sort:
            params["sort"] = sort

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                return NocoDBRecordsResponse(**data)
            except httpx.HTTPStatusError as e:
                logger.error(f"NocoDB HTTP Error {e.response.status_code}: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Failed to query NocoDB records: {e}")
                raise

    async def fetch_all_records(
        self,
        since_timestamp: Optional[str] = None,
        batch_size: int = 100,
    ) -> List[dict]:
        """
        Paginates through all customer records from NocoDB.
        If since_timestamp is provided, filters for changes since that time.
        """
        records: List[dict] = []
        offset = 0
        where_filter = build_updated_since_filter(since_timestamp)

        while True:
            logger.info(f"Fetching NocoDB page at offset {offset} (limit: {batch_size})...")
            page_data = await self.get_records_page(
                offset=offset,
                limit=batch_size,
                where_clause=where_filter,
                sort="Id",
            )
            batch = page_data.list
            if not batch:
                break

            records.extend(batch)
            offset += len(batch)

            # Check if this was the last page
            if page_data.pageInfo and page_data.pageInfo.isLastPage:
                break
            if len(batch) < batch_size:
                break

        logger.info(f"Retrieved {len(records)} total records from NocoDB.")
        return records
