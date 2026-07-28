"""Administrative API — source registry and document metadata."""

from relocate_helper.admin.routes import router as admin_router
from relocate_helper.admin.sources import SourceRegistryService

__all__ = ["SourceRegistryService", "admin_router"]
