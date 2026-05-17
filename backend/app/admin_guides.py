"""Admin guides endpoints for managing markdown guide files."""

import asyncio
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.admin_auth import verify_admin_key
from backend.app.admin_schemas import GuideContent, GuideMeta
from backend.app.s3_client import S3Client, S3DownloadError, S3UploadError

logger = logging.getLogger(__name__)

guides_router = APIRouter()
s3_client = S3Client()

GUIDES_PREFIX = "guides/"
INTENT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _sanitize_intent(intent: str) -> str:
    """Validate intent string against allowed characters.

    Args:
        intent: The intent string to validate.

    Returns:
        The sanitized intent string.

    Raises:
        HTTPException: 422 if intent contains invalid characters.
    """
    if not INTENT_PATTERN.match(intent):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid intent format: {intent}",
        )
    return intent


@guides_router.get("/guides", response_model=list[GuideMeta])
async def admin_list_guides(
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> list[GuideMeta]:
    """List all markdown guides under the guides/ prefix.

    Returns:
        List of GuideMeta objects.
    """
    try:
        objects = await s3_client.list_objects(prefix=GUIDES_PREFIX)
    except S3DownloadError as e:
        logger.error("Failed to list guides: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list guides",
        ) from e

    guides: list[GuideMeta] = []
    for obj in objects:
        key: str = obj.get("Key", "")
        if not key.endswith(".md"):
            continue
        filename = key.split("/")[-1]
        intent = filename.replace(".md", "")
        last_modified = obj.get("LastModified")
        updated_at = None
        if last_modified is not None:
            try:
                from datetime import datetime

                if isinstance(last_modified, datetime):
                    updated_at = last_modified.isoformat()
                else:
                    updated_at = str(last_modified)
            except Exception:
                updated_at = str(last_modified)
        guides.append(
            GuideMeta(
                intent=intent,
                title=intent.replace("_", " ").replace("-", " ").title(),
                updated_at=updated_at,
            )
        )

    return guides


@guides_router.get("/guides/{intent}", response_model=GuideContent)
async def admin_get_guide(
    intent: str,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> GuideContent:
    """Download a single guide markdown file.

    Args:
        intent: The guide intent identifier.

    Returns:
        GuideContent with the markdown text.

    Raises:
        HTTPException: 404 if guide not found.
    """
    sanitized = _sanitize_intent(intent)
    key = f"{GUIDES_PREFIX}{sanitized}.md"

    try:
        data = await asyncio.to_thread(s3_client.download_pdf, key)
    except S3DownloadError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg or "nosuchkey" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Guide not found: {sanitized}",
            ) from e
        logger.error("Failed to download guide: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download guide",
        ) from e

    content = data.decode("utf-8")
    return GuideContent(intent=sanitized, content=content)


@guides_router.put("/guides/{intent}", response_model=GuideContent)
async def admin_update_guide(
    intent: str,
    data: GuideContent,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> GuideContent:
    """Upload or overwrite a guide markdown file.

    Args:
        intent: The guide intent identifier.
        data: GuideContent payload.

    Returns:
        The saved guide content.

    Raises:
        HTTPException: 422 if intent invalid or body empty.
    """
    sanitized = _sanitize_intent(intent)
    if not data.content or not data.content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Guide content cannot be empty",
        )

    key = f"{GUIDES_PREFIX}{sanitized}.md"
    body = data.content.encode("utf-8")

    try:
        await asyncio.to_thread(
            s3_client.put_object,
            key=key,
            data=body,
            content_type="text/markdown",
        )
    except S3UploadError as e:
        logger.error("Failed to upload guide: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save guide",
        ) from e

    return GuideContent(intent=sanitized, content=data.content)


@guides_router.delete("/guides/{intent}")
async def admin_delete_guide(
    intent: str,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> dict[str, bool]:
    """Delete a guide markdown file.

    Args:
        intent: The guide intent identifier.

    Returns:
        Confirmation dict with deleted=True.

    Raises:
        HTTPException: 404 if guide not found.
    """
    sanitized = _sanitize_intent(intent)
    key = f"{GUIDES_PREFIX}{sanitized}.md"

    try:
        await s3_client.head_object(key)
    except S3DownloadError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg or "nosuchkey" in error_msg or "404" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Guide not found: {sanitized}",
            ) from e
        logger.error("Failed to check guide existence: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify guide existence",
        ) from e

    try:
        await s3_client.delete_object(key)
    except S3UploadError as e:
        logger.error("Failed to delete guide: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete guide",
        ) from e

    return {"deleted": True}
