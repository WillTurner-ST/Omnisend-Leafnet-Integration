import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env file from project root or middleware directory
BASE_DIR = Path(__file__).resolve().parent.parent
dotenv_path = BASE_DIR / ".env"
if not dotenv_path.exists():
    dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path)


class Settings(BaseModel):
    # Application settings
    app_name: str = "Leafnet-NocoDB to Omnisend Middleware"
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    sync_interval_hours: int = Field(default_factory=lambda: int(os.getenv("SYNC_INTERVAL_HOURS", "24")))
    db_path: str = Field(default_factory=lambda: os.getenv("DB_PATH", str(BASE_DIR / "middleware.db")))

    # Omnisend API Configuration
    omnisend_api_key: str = Field(default_factory=lambda: os.getenv("OMNISEND_API_KEY", ""))
    omnisend_base_url: str = Field(
        default_factory=lambda: os.getenv("OMNISEND_BASE_URL", "https://api.omnisend.com/v3")
    )

    # NocoDB API Configuration
    nocodb_api_url: str = Field(
        default_factory=lambda: os.getenv("NOCODB_API_URL", "https://app.nocodb.com")
    )
    nocodb_api_token: str = Field(default_factory=lambda: os.getenv("NOCODB_API_TOKEN", ""))
    nocodb_table_id: str = Field(default_factory=lambda: os.getenv("NOCODB_TABLE_ID", ""))
    nocodb_page_size: int = Field(default_factory=lambda: int(os.getenv("NOCODB_PAGE_SIZE", "100")))

    # Leafnet API Configuration
    leafnet_api_url: str = Field(
        default_factory=lambda: os.getenv("LEAFNET_API_URL", "https://snapdragon-hemp.haimenu.com/api/")
    )
    leafnet_api_key: str = Field(
        default_factory=lambda: os.getenv("LEAFNET_API_KEY", "")
    )
    leafnet_folder_name: str = Field(
        default_factory=lambda: os.getenv("LEAFNET_FOLDER_NAME", "snapdragon-hemp")
    )

    # Webhook Secret (optional token for validating incoming webhooks)
    webhook_secret: Optional[str] = Field(default_factory=lambda: os.getenv("WEBHOOK_SECRET", None))

    # VIP spend threshold cutoff for tag segmentation
    vip_spend_threshold: float = Field(default_factory=lambda: float(os.getenv("VIP_SPEND_THRESHOLD", "500.0")))


settings = Settings()
