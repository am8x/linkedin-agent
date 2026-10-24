"""Unit tests for LinkedIn post ingestion and media extraction (User Story 1)."""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
import pytest

from src.linkedin.client import LinkedInClient
from src.linkedin.models import LinkedInAPIError, LinkedInPostDetails


def make_client(handler: Any, **kwargs: Any) -> LinkedInClient:
    transport = httpx.MockTransport(handler)
    return LinkedInClient(
        "test-token", person_urn="12345", transport=transport, **kwargs
    )


POST_JSON_TEXT_ONLY = {
    "id": "urn:li:activity:7518646093870510081",
    "author": "urn:li:organization:123456",
    "commentary": "Here is our latest technical benchmark comparing model architectures...",
    "lifecycleState": "PUBLISHED",
    "visibility": "PUBLIC",
}

POST_JSON_WITH_IMAGE = {
    "id": "urn:li:activity:7518646093870510081",
    "author": "urn:li:person:8675309",
    "commentary": "Check out this system architecture diagram for our new pipeline.",
    "content": {
        "media": {
            "id": "urn:li:digitalmediaAsset:D5605AQE12345",
            "title": "architecture_diagram.png",
        }
    },
    "lifecycleState": "PUBLISHED",
    "visibility": "PUBLIC",
}

POST_JSON_WITH_MEDIA_URL = {
    "id": "urn:li:activity:7518646093870510081",
    "author": "urn:li:organization:123456",
    "commentary": "Visual benchmark results.",
    "content": {
        "media": {
            "downloadUrl": "https://media.licdn.com/dms/image/v2/test.png",
            "title": "benchmark.png",
        }
    },
    "lifecycleState": "PUBLISHED",
    "visibility": "PUBLIC",
}


@pytest.mark.asyncio
async def test_get_post_text_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert urllib.parse.quote(
            "urn:li:activity:7518646093870510081", safe=""
        ) in str(request.url)
        assert request.headers["X-Restli-Protocol-Version"] == "2.0.0"
        assert request.headers["LinkedIn-Version"] == "202511"
        return httpx.Response(200, json=POST_JSON_TEXT_ONLY)

    async with make_client(handler) as client:
        post = await client.get_post("urn:li:activity:7518646093870510081")
        assert isinstance(post, LinkedInPostDetails)
        assert post.post_urn == "urn:li:activity:7518646093870510081"
        assert post.author_urn == "urn:li:organization:123456"
        assert "technical benchmark" in post.commentary_text
        assert post.has_image is False
        assert post.media.media_type == "NONE"


@pytest.mark.asyncio
async def test_get_post_with_image_asset() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=POST_JSON_WITH_IMAGE)

    async with make_client(handler) as client:
        post = await client.get_post("urn:li:activity:7518646093870510081")
        assert post.has_image is True
        assert post.media.media_type == "IMAGE"
        assert post.media.asset_urn == "urn:li:digitalmediaAsset:D5605AQE12345"
        assert post.media.title == "architecture_diagram.png"


@pytest.mark.asyncio
async def test_get_post_with_media_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=POST_JSON_WITH_MEDIA_URL)

    async with make_client(handler) as client:
        post = await client.get_post("urn:li:activity:7518646093870510081")
        assert post.has_image is True
        assert post.media.media_url == "https://media.licdn.com/dms/image/v2/test.png"


@pytest.mark.asyncio
async def test_get_post_fallback_to_ugc_on_404() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        requested_urls.append(url_str)
        if "activity" in url_str:
            return httpx.Response(404, json={"message": "Post not found"})
        if "ugcPost" in url_str:
            data = dict(POST_JSON_TEXT_ONLY)
            data["id"] = "urn:li:ugcPost:7518646093870510081"
            return httpx.Response(200, json=data)
        return httpx.Response(404, json={"message": "Not found"})

    async with make_client(handler) as client:
        post = await client.get_post("urn:li:activity:7518646093870510081")
        assert post.post_urn == "urn:li:ugcPost:7518646093870510081"
        assert len(requested_urls) == 2


@pytest.mark.asyncio
async def test_get_post_404_raises_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not found"})

    async with make_client(handler) as client:
        with pytest.raises(LinkedInAPIError) as exc_info:
            await client.get_post("urn:li:activity:7518646093870510081")
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_post_401_unauthorized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    async with make_client(handler) as client:
        with pytest.raises(LinkedInAPIError) as exc_info:
            await client.get_post("urn:li:activity:7518646093870510081")
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_post_403_forbidden() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden"})

    async with make_client(handler) as client:
        with pytest.raises(LinkedInAPIError) as exc_info:
            await client.get_post("urn:li:activity:7518646093870510081")
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_fetch_image_bytes_success() -> None:
    fake_png = b"\x89PNG\r\n\x1a\nfakeimagebytes"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=fake_png, headers={"Content-Type": "image/png"}
        )

    async with make_client(handler) as client:
        data, content_type = await client.fetch_image_bytes(
            "https://media.licdn.com/test.png"
        )
        assert data == fake_png
        assert content_type == "image/png"


@pytest.mark.asyncio
async def test_fetch_image_bytes_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"Server error")

    async with make_client(handler) as client:
        with pytest.raises(LinkedInAPIError):
            await client.fetch_image_bytes("https://media.licdn.com/bad.png")
