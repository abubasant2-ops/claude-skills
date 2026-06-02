"""S3-compatible object storage (MinIO in dev, S3/STC Cloud in prod)."""

from __future__ import annotations

import uuid
from typing import BinaryIO

import boto3
from botocore.client import Config

from app.core.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def upload_file(
    *,
    file_obj: BinaryIO,
    organization_id: str,
    project_id: str,
    filename: str,
    content_type: str | None = None,
) -> str:
    """Returns the storage key."""
    key = f"org/{organization_id}/projects/{project_id}/{uuid.uuid4()}_{filename}"
    extra = {"ContentType": content_type} if content_type else {}
    _client().upload_fileobj(file_obj, settings.s3_bucket, key, ExtraArgs=extra)
    return key


def download_to_path(storage_key: str, target_path: str) -> None:
    _client().download_file(settings.s3_bucket, storage_key, target_path)


def presign_url(storage_key: str, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": storage_key},
        ExpiresIn=expires_in,
    )
