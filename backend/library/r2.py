"""Private R2 Standard objects. No public bucket or credentials in page responses."""

import hashlib
from datetime import timedelta
from pathlib import PurePosixPath
from urllib.parse import quote

import boto3
from botocore.config import Config
from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone

from .models import CloudObject, Video


class StorageError(Exception):
    pass


def client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        region_name="auto",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 3, "mode": "standard"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def valid_key(key):
    path = PurePosixPath(key)
    if not key or not key.startswith(settings.R2_PREFIX + "/") or ".." in path.parts or "\\" in key:
        raise StorageError("Invalid object key.")
    return key


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def signed_url(key, method="GET", attachment_name=None):
    valid_key(key)
    params = {"Bucket": settings.R2_BUCKET_NAME, "Key": key}
    if attachment_name:
        params["ResponseContentDisposition"] = "attachment; filename=video." + ("m4a" if key.endswith(".m4a") else "mp4") + "; filename*=UTF-8''" + quote(attachment_name, safe="")
    return client().generate_presigned_url(
        "head_object" if method == "HEAD" else "get_object",
        Params=params,
        ExpiresIn=settings.DOWNLOAD_URL_TTL if attachment_name else settings.R2_URL_TTL,
    )


def upload(path, record, content_type):
    """Register record BEFORE upload so an interrupted request never loses cleanup intent."""
    valid_key(record.key)
    try:
        store = client()
        store.upload_file(
            str(path),
            settings.R2_BUCKET_NAME,
            record.key,
            ExtraArgs={
                "ContentType": content_type,
                "StorageClass": "STANDARD",
                "CacheControl": "private, no-store",
                "Metadata": {"sha256": record.sha256},
            },
        )
        head = store.head_object(Bucket=settings.R2_BUCKET_NAME, Key=record.key)
        if (
            head["ContentLength"] != record.size_bytes
            or head.get("Metadata", {}).get("sha256") != record.sha256
        ):
            raise StorageError("Uploaded object verification failed.")
    except Exception as exc:
        raise StorageError("Object upload failed; retry is safe.") from exc


def download(key, destination, expected=None):
    try:
        client().download_file(settings.R2_BUCKET_NAME, valid_key(key), str(destination))
        if expected and checksum(destination) != expected:
            raise StorageError("Downloaded object checksum mismatch.")
    except Exception as exc:
        raise StorageError("Object download or verification failed.") from exc


def stored_bytes():
    # Retained deleted objects and pending uploads still occupy the storage budget.
    return (CloudObject.objects.aggregate(n=Sum("size_bytes"))["n"] or 0) + (
        Video.objects.filter(storage_backend="local").aggregate(n=Sum("size_bytes"))["n"] or 0
    )


def defer_delete(objects):
    objects.update(
        state="deleting",
        delete_after=timezone.now(),
    )


def cleanup(check_lease=lambda: None):
    """Worker only. Idempotent deletion retries; never delete a referenced ready object."""
    stale = CloudObject.objects.filter(
        state="pending", created_at__lt=timezone.now() - timedelta(days=1)
    )
    defer_delete(stale)
    for record in CloudObject.objects.filter(
        state="deleting", delete_after__lte=timezone.now()
    ).order_by("pk")[:100]:
        check_lease()
        if (
            Video.objects.filter(status="ready")
            .filter(
                Q(file_name=record.key) | Q(audio_name=record.key) | Q(thumbnail_name=record.key)
            )
            .exists()
        ):
            continue
        try:
            client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=valid_key(record.key))
        except Exception:
            record.attempts += 1
            record.error = "delete_failed"
            record.delete_after = timezone.now() + timedelta(
                minutes=min(60, 2 ** min(record.attempts, 6))
            )
            record.save(update_fields=["attempts", "error", "delete_after"])
        else:
            record.delete()
