from middleware.database.db import Database
from middleware.config import settings

db = Database(settings.db_path)

__all__ = ["Database", "db"]
