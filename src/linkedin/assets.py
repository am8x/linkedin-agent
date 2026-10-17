"""The three-step LinkedIn image publication workflow.

``registerUpload`` → ``PUT`` binary → ``ugcPosts`` assembled into one call so
the publisher agent stays declarative.  No network access happens here beyond
delegating to :class:`src.linkedin.client.LinkedInClient`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.linkedin.client import LinkedInClient
from src.linkedin.models import LinkedInPostResult
from src.logging import get_logger

logger = get_logger(__name__)


class LinkedInAssetPublisher:
    """Publishes an image + commentary pair to a LinkedIn member profile."""

    def __init__(self, client: LinkedInClient) -> None:
        self.client = client

    async def upload_image(
        self,
        file_path: str | Path,
        *,
        content_type: str = "image/png",
    ) -> str:
        """Register and upload an image, returning its asset URN."""
        path = Path(file_path)
        registered = await self.client.register_upload()
        await self.client.upload_binary(
            registered.upload_url,
            path,
            content_type=content_type,
        )
        logger.info("Uploaded image asset %s", registered.asset_urn)
        return registered.asset_urn

    async def publish(
        self,
        *,
        commentary: str,
        image_path: str | Path | None = None,
        title: str | None = None,
        visibility: str = "PUBLIC",
    ) -> LinkedInPostResult:
        """Publish commentary, optionally attached to an uploaded image."""
        asset_urn: str | None = None
        if image_path is not None:
            asset_urn = await self.upload_image(image_path)

        post = await self.client.create_post(
            commentary=commentary,
            asset_urn=asset_urn,
            title=title,
            visibility=visibility,
        )
        return LinkedInPostResult(
            post_urn=post.post_urn,
            asset_urn=asset_urn,
            commentary=commentary,
        )


async def publish_image_post(
    client: LinkedInClient,
    *,
    commentary: str,
    image_path: str | Path | None = None,
    title: str | None = None,
) -> LinkedInPostResult:
    """Convenience wrapper around :class:`LinkedInAssetPublisher`."""
    publisher = LinkedInAssetPublisher(client)
    return await publisher.publish(
        commentary=commentary,
        image_path=image_path,
        title=title,
    )


def build_publisher(client: Any) -> LinkedInAssetPublisher:
    """Adapt an already-constructed client into an asset publisher."""
    return LinkedInAssetPublisher(client)


__all__ = [
    "LinkedInAssetPublisher",
    "build_publisher",
    "publish_image_post",
]
