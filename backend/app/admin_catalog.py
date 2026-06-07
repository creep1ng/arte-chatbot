"""Admin catalog endpoints for managing the product catalog index."""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.app.admin_auth import verify_admin_key
from backend.app.admin_schemas import CatalogIndex
from backend.app.catalog import get_catalog, reload_catalog, save_catalog
from backend.app.s3_client import S3Client, S3DownloadError

logger = logging.getLogger(__name__)

catalog_router = APIRouter()
s3_client = S3Client()


@catalog_router.get("/catalog", response_model=CatalogIndex)
async def admin_get_catalog(
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> CatalogIndex:
    """Download and validate the current catalog index from S3.

    Returns:
        CatalogIndex model containing all products.
    """
    try:
        catalog = get_catalog(force_reload=False)
        products = [p.model_dump() for p in catalog.products]
        return CatalogIndex(products=products)
    except Exception as e:
        logger.error("Failed to load catalog: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load catalog index",
        ) from e


@catalog_router.put("/catalog", response_model=CatalogIndex)
async def admin_put_catalog(
    data: CatalogIndex,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
    if_match: Optional[str] = Header(None),
) -> CatalogIndex:
    """Update the catalog index with optimistic locking.

    Args:
        data: The new catalog index.
        if_match: ETag of the current catalog index for optimistic locking.

    Returns:
        The saved catalog index.

    Raises:
        HTTPException: 409 if ETag mismatch, 500 on S3 errors.
    """
    if if_match is not None:
        try:
            metadata = await s3_client.head_object("index/catalog_index.json")
            current_etag = metadata.get("ETag", "")
            if current_etag != if_match:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Catalog index was modified by another user",
                )
        except S3DownloadError as e:
            error_msg = str(e).lower()
            if (
                "not found" in error_msg
                or "404" in error_msg
                or "nosuchkey" in error_msg
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Catalog index was modified by another user",
                ) from e
            logger.error("S3 head_object failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to check catalog index version",
            ) from e

    try:
        save_catalog(data.model_dump())
        reload_catalog()
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to save catalog: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save catalog index",
        ) from e
