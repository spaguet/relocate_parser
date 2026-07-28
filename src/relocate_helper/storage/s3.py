"""S3-compatible ObjectStorage backend using aiobotocore."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiobotocore.session import AioSession, get_session
from botocore.exceptions import ClientError

from relocate_helper.common.config import Settings
from relocate_helper.storage.exceptions import ObjectNotFoundError, StorageError
from relocate_helper.storage.protocol import StoredObjectMeta


def _is_not_found(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


@dataclass
class S3ObjectStorage:
    """Async S3/MinIO storage with optional server-side encryption."""

    settings: Settings
    _session: AioSession = field(default_factory=get_session, repr=False)

    @property
    def bucket(self) -> str:
        return self.settings.s3_bucket

    def _client_kwargs(self) -> dict[str, object]:
        return {
            "service_name": "s3",
            "endpoint_url": self.settings.s3_endpoint_url,
            "aws_access_key_id": self.settings.s3_access_key.get_secret_value(),
            "aws_secret_access_key": self.settings.s3_secret_key.get_secret_value(),
            "region_name": self.settings.s3_region,
            "use_ssl": self.settings.s3_use_ssl,
        }

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        mime_type: str,
        content_hash: str,
        server_side_encryption: bool = True,
    ) -> StoredObjectMeta:
        put_kwargs: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": mime_type,
            "Metadata": {"content-hash": content_hash},
        }
        if server_side_encryption and self.settings.s3_server_side_encryption:
            put_kwargs["ServerSideEncryption"] = "AES256"

        try:
            async with self._session.create_client("s3", **self._client_kwargs()) as client:
                if await self.exists(key):
                    head = await self.head(key)
                    if head.content_hash == content_hash:
                        return head
                    msg = f"key {key} already holds different content"
                    raise StorageError(msg)

                response = await client.put_object(**put_kwargs)
                etag = response.get("ETag")
                if isinstance(etag, str):
                    etag = etag.strip('"')
                return StoredObjectMeta(
                    key=key,
                    content_hash=content_hash,
                    mime_type=mime_type,
                    size_bytes=len(data),
                    etag=etag,
                )
        except ClientError as exc:
            raise StorageError(str(exc)) from exc

    async def get(self, key: str) -> bytes:
        try:
            async with self._session.create_client("s3", **self._client_kwargs()) as client:
                response = await client.get_object(Bucket=self.bucket, Key=key)
                body = response["Body"]
                data = await body.read()
                return bytes(data)
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise StorageError(str(exc)) from exc

    async def head(self, key: str) -> StoredObjectMeta:
        try:
            async with self._session.create_client("s3", **self._client_kwargs()) as client:
                response = await client.head_object(Bucket=self.bucket, Key=key)
                metadata = response.get("Metadata") or {}
                content_hash = str(metadata.get("content-hash", ""))
                mime_type = str(response.get("ContentType", "application/octet-stream"))
                size = int(response.get("ContentLength", 0))
                etag = response.get("ETag")
                if isinstance(etag, str):
                    etag = etag.strip('"')
                if not content_hash:
                    content_hash = etag or key.rsplit("/", maxsplit=1)[-1]
                return StoredObjectMeta(
                    key=key,
                    content_hash=content_hash,
                    mime_type=mime_type,
                    size_bytes=size,
                    etag=etag,
                )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise StorageError(str(exc)) from exc

    async def delete(self, key: str) -> None:
        try:
            async with self._session.create_client("s3", **self._client_kwargs()) as client:
                await client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                return
            raise StorageError(str(exc)) from exc

    async def exists(self, key: str) -> bool:
        try:
            await self.head(key)
        except ObjectNotFoundError:
            return False
        return True
