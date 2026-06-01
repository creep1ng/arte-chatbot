"""Admin S3 explorer endpoints.

These endpoints expose safe, authenticated operations for browsing and mutating
the chatbot knowledge-base bucket without exposing AWS credentials to the
browser.
"""

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.admin_auth import verify_admin_key
from backend.app.admin_schemas import (
    DeleteS3ObjectsRequest,
    PresignedUploadRequest,
    PresignedUploadResponse,
    S3TreeNode,
)
from backend.app.s3_client import (
    S3Client,
    S3DownloadError,
    S3ObjectNotFoundError,
    S3UploadError,
)

s3_router = APIRouter(prefix="/s3")
s3_client = S3Client()

ALLOWED_READ_PREFIXES = ("", "raw/", "guides/", "index/")
ALLOWED_WRITE_PREFIXES = ("raw/", "guides/", "index/")
KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_\-/.]+$")


def _validate_s3_key(key: str, allowed_prefixes: tuple[str, ...]) -> None:
    """Validate a browser-provided S3 key/prefix.

    Args:
        key: S3 key or prefix to validate.
        allowed_prefixes: Prefix allowlist for the operation.

    Raises:
        HTTPException: If the key is unsafe or outside allowed prefixes.
    """
    if key.startswith("/") or ".." in key or not KEY_PATTERN.match(key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid S3 key",
        )

    if not any(key.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="S3 key prefix is not allowed",
        )


def _format_last_modified(value: Any) -> str | None:
    """Format boto3 LastModified values as ISO-8601 strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _insert_tree_object(
    roots: dict[str, dict[str, Any]],
    key: str,
    size: int | None,
    last_modified: str | None,
) -> None:
    """Insert a flat S3 object key into a hierarchical node map."""
    parts = [part for part in key.split("/") if part]
    if not parts:
        return

    current = roots
    path_parts: list[str] = []
    for index, part in enumerate(parts):
        path_parts.append(part)
        node_key = "/".join(path_parts)
        is_file = index == len(parts) - 1

        if part not in current:
            current[part] = {
                "node": S3TreeNode(
                    name=part,
                    key=node_key,
                    type="file" if is_file else "folder",
                    size=size if is_file else None,
                    last_modified=last_modified if is_file else None,
                    children=None if is_file else [],
                ),
                "children": {},
            }

        if not is_file:
            current = current[part]["children"]


def _materialize_tree(nodes: dict[str, dict[str, Any]]) -> list[S3TreeNode]:
    """Convert internal nested maps into sorted S3TreeNode objects."""
    result: list[S3TreeNode] = []
    for entry in nodes.values():
        node = entry["node"]
        children = entry["children"]
        if node.type == "folder":
            node.children = _materialize_tree(children)
        result.append(node)
    return sorted(result, key=lambda node: (node.type, node.name))


def _build_tree(objects: list[dict[str, Any]]) -> list[S3TreeNode]:
    """Build a stable S3 tree from boto3 object summaries."""
    roots: dict[str, dict[str, Any]] = {}
    for obj in objects:
        key = str(obj.get("Key", ""))
        _insert_tree_object(
            roots,
            key=key,
            size=obj.get("Size"),
            last_modified=_format_last_modified(obj.get("LastModified")),
        )
    return _materialize_tree(roots)


@s3_router.get("/tree", response_model=list[S3TreeNode])
async def get_s3_tree(
    _admin_key: Annotated[str, Depends(verify_admin_key)],
    prefix: Annotated[str, Query()] = "raw/",
) -> list[S3TreeNode]:
    """Return a hierarchical view of S3 objects under a safe prefix."""
    _validate_s3_key(prefix, ALLOWED_READ_PREFIXES)
    try:
        objects = await s3_client.list_objects(prefix=prefix)
    except S3DownloadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _build_tree(objects)


@s3_router.post("/presigned-upload", response_model=PresignedUploadResponse)
async def create_presigned_upload(
    payload: PresignedUploadRequest,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> PresignedUploadResponse:
    """Create a presigned POST for direct browser upload to S3."""
    _validate_s3_key(payload.key, ALLOWED_WRITE_PREFIXES)
    try:
        await s3_client.head_object(payload.key)
    except S3ObjectNotFoundError:
        pass
    except S3DownloadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="S3 object already exists",
        )

    try:
        presigned = await s3_client.generate_presigned_post(
            key=payload.key,
            content_type=payload.content_type,
        )
    except S3UploadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return PresignedUploadResponse(
        url=presigned["url"],
        fields=presigned.get("fields", {}),
        key=payload.key,
    )


@s3_router.delete("/objects")
async def delete_s3_objects(
    payload: DeleteS3ObjectsRequest,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> dict[Literal["deleted"], int]:
    """Delete one or more safe-prefix S3 objects."""
    if not payload.keys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one key is required",
        )

    for key in payload.keys:
        _validate_s3_key(key, ALLOWED_WRITE_PREFIXES)

    try:
        await s3_client.delete_objects(payload.keys)
    except S3UploadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"deleted": len(payload.keys)}
