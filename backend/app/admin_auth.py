"""Admin authentication wrapper.

Re-exports verify_admin_key so that admin routers can import it cleanly
from a dedicated auth module without pulling in the generic auth module.
"""

from backend.app.auth import verify_admin_key

__all__ = ["verify_admin_key"]
