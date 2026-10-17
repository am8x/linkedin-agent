"""Unit tests for the LinkedIn REST v2 models, client, and asset workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from src.linkedin.assets import LinkedInAssetPublisher, publish_image_post
from src.linkedin.client import (
    REGISTER_UPLOAD_PATH,
    UGC_POSTS_PATH,
    LinkedInClient,
    build_client,
)
from src.linkedin.models import (
    RECIPE_FEEDSHARE_IMAGE,
    SERVICE_RELATIONSHIP_IDENTIFIER,
    UGC_SHARE_CONTENT_KEY,
    UGC_VISIBILITY_KEY,
    LinkedInAPIError,
    LinkedInPostResult,
    PublicationRecord,
    RegisterUploadRequest,
    RegisterUploadResponse,
    ShareContent,
    UgcPostRequest,
    UgcPostResponse,
    ensure_person_urn,
)
from tests.conftest import make_png_bytes

REGISTER_RESPONSE = {
    "value": {
        "asset": "urn:li:digitalmediaAsset:C5622AQH1234",
        "uploadMechanism": {
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {
                "uploadUrl": "https://www.linkedin.com/dms-uploads/abc/uploaded-image.jpg",
            }
        },
    }
}


# ---------------------------------------------------------------------------
# T021 — payload models
# ---------------------------------------------------------------------------
class TestPayloadModels:
    def test_register_upload_request_shape(self) -> None:
        payload = RegisterUploadRequest.for_person("12345").to_payload()
        request = payload["registerUploadRequest"]
        assert request["recipes"] == [RECIPE_FEEDSHARE_IMAGE]
        assert request["owner"] == "urn:li:person:12345"
        assert request["serviceRelationships"][0]["identifier"] == (
            SERVICE_RELATIONSHIP_IDENTIFIER
        )
        assert request["supportedUploadMechanism"] == ["SYNCHRONOUS_UPLOAD"]

    def test_register_upload_request_normalises_existing_urn(self) -> None:
        payload = RegisterUploadRequest.for_person("urn:li:person:99").to_payload()
        assert payload["registerUploadRequest"]["owner"] == "urn:li:person:99"

    def test_register_upload_response_parsing(self) -> None:
        parsed = RegisterUploadResponse.from_payload(REGISTER_RESPONSE)
        assert parsed.asset_urn == "urn:li:digitalmediaAsset:C5622AQH1234"
        assert parsed.upload_url.startswith("https://www.linkedin.com/dms-uploads/")

    def test_register_upload_response_requires_asset_and_url(self) -> None:
        with pytest.raises(LinkedInAPIError, match="missing the asset URN"):
            RegisterUploadResponse.from_payload({"value": {}})

    def test_register_upload_response_rejects_non_asset_urn(self) -> None:
        with pytest.raises(ValidationError):
            RegisterUploadResponse(
                asset_urn="urn:li:share:1",
                upload_url="https://example.com/upload",
            )

    def test_register_upload_response_rejects_non_https_upload_url(self) -> None:
        with pytest.raises(ValidationError):
            RegisterUploadResponse(
                asset_urn="urn:li:digitalmediaAsset:1",
                upload_url="http://insecure.example.com/upload",
            )

    def test_share_content_without_media(self) -> None:
        content = ShareContent(commentary="hello").to_payload()
        assert content["shareCommentary"] == {"text": "hello"}
        assert content["shareMediaCategory"] == "IMAGE"
        assert "media" not in content

    def test_share_content_with_media_and_title(self) -> None:
        content = ShareContent(
            commentary="hello",
            media_urn="urn:li:digitalmediaAsset:1",
            media_title="card",
        ).to_payload()
        assert content["media"][0]["status"] == "READY"
        assert content["media"][0]["media"] == "urn:li:digitalmediaAsset:1"
        assert content["media"][0]["title"] == {"text": "card"}

    def test_ugc_post_request_shape(self) -> None:
        payload = UgcPostRequest(
            author="12345",
            commentary="a take",
            media_urn="urn:li:digitalmediaAsset:1",
        ).to_payload()
        assert payload["author"] == "urn:li:person:12345"
        assert payload["lifecycleState"] == "PUBLISHED"
        assert UGC_SHARE_CONTENT_KEY in payload["specificContent"]
        assert payload["visibility"] == {UGC_VISIBILITY_KEY: "PUBLIC"}
        share = payload["specificContent"][UGC_SHARE_CONTENT_KEY]
        assert share["shareCommentary"]["text"] == "a take"

    def test_ugc_post_request_rejects_blank_commentary(self) -> None:
        with pytest.raises(ValidationError):
            UgcPostRequest(author="1", commentary="   ")

    def test_ugc_post_response_reads_body_id(self) -> None:
        assert UgcPostResponse.from_payload({"id": "urn:li:share:1"}).post_urn == (
            "urn:li:share:1"
        )

    def test_ugc_post_response_falls_back_to_restli_header(self) -> None:
        parsed = UgcPostResponse.from_payload(
            {}, response_headers={"x-restli-id": "urn:li:share:2"}
        )
        assert parsed.post_urn == "urn:li:share:2"

    def test_ugc_post_response_requires_a_urn(self) -> None:
        with pytest.raises(LinkedInAPIError, match="did not include a post URN"):
            UgcPostResponse.from_payload({})

    def test_ensure_person_urn_variants(self) -> None:
        assert ensure_person_urn("123") == "urn:li:person:123"
        assert ensure_person_urn("urn:li:person:123") == "urn:li:person:123"
        assert ensure_person_urn("urn:li:organization:9") == "urn:li:organization:9"


class TestDomainModels:
    def test_post_result_converts_to_a_publication_record(self) -> None:
        result = LinkedInPostResult(
            post_urn="urn:li:share:1",
            asset_urn="urn:li:digitalmediaAsset:1",
            commentary="a take",
        )
        record = result.to_publication_record(tweet_id="9", author_handle="sama")
        assert isinstance(record, PublicationRecord)
        assert record.status == "PUBLISHED"
        assert record.succeeded is True
        assert record.published_at is not None
        assert record.published_at.tzinfo == UTC

    def test_publication_record_accepts_every_status(self) -> None:
        for status in ("PUBLISHED", "SKIPPED", "DRY_RUN", "FAILED"):
            assert (
                PublicationRecord(
                    tweet_id="1",
                    author_handle="a",
                    status=status,  # type: ignore[arg-type]
                ).status
                == status
            )

    def test_publication_record_rejects_unknown_status(self) -> None:
        with pytest.raises(ValidationError):
            PublicationRecord(tweet_id="1", author_handle="a", status="MAYBE")

    def test_publication_record_normalises_naive_timestamp(self) -> None:
        record = PublicationRecord(
            tweet_id="1",
            author_handle="a",
            status="PUBLISHED",
            published_at=datetime(2026, 10, 17, 12, 0),
        )
        assert record.published_at.tzinfo == UTC


# ---------------------------------------------------------------------------
# T022 — client
# ---------------------------------------------------------------------------
def make_client(handler: Any, **kwargs: Any) -> LinkedInClient:
    transport = httpx.MockTransport(handler)
    return LinkedInClient(
        "test-token", person_urn="12345", transport=transport, **kwargs
    )


class TestLinkedInClient:
    def test_requires_an_access_token(self) -> None:
        with pytest.raises(LinkedInAPIError, match="access token is required"):
            LinkedInClient("")

    def test_default_headers_include_oauth_and_protocol_version(self) -> None:
        client = make_client(lambda request: httpx.Response(200, json={}))
        headers = client.default_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["X-Restli-Protocol-Version"] == "2.0.0"
        assert "LinkedIn-Version" in headers

    async def test_register_upload_posts_the_expected_payload(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["query"] = request.url.query.decode()
            seen["body"] = request.content.decode()
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=REGISTER_RESPONSE)

        client = make_client(handler)
        try:
            parsed = await client.register_upload()
        finally:
            await client.aclose()

        assert parsed.asset_urn == "urn:li:digitalmediaAsset:C5622AQH1234"
        assert seen["path"] == "/v2/assets"
        assert seen["query"] == "action=registerUpload"
        assert "registerUploadRequest" in seen["body"]
        assert seen["auth"] == "Bearer test-token"

    async def test_upload_binary_puts_the_file_bytes(self, tmp_path: Path) -> None:
        image = tmp_path / "card.png"
        image.write_bytes(make_png_bytes(16, 16))
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["content_type"] = request.headers.get("content-type")
            seen["length"] = len(request.content)
            return httpx.Response(201)

        client = make_client(handler)
        try:
            await client.upload_binary("https://upload.example.com/x", image)
        finally:
            await client.aclose()

        assert seen["method"] == "PUT"
        assert seen["content_type"] == "image/png"
        assert seen["length"] == image.stat().st_size

    async def test_upload_binary_rejects_a_missing_file(self, tmp_path: Path) -> None:
        client = make_client(lambda request: httpx.Response(201))
        try:
            with pytest.raises(LinkedInAPIError, match="does not exist"):
                await client.upload_binary(
                    "https://upload.example.com/x", tmp_path / "nope.png"
                )
        finally:
            await client.aclose()

    async def test_create_post_sends_the_ugc_payload(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = request.content.decode()
            return httpx.Response(
                201,
                json={"id": "urn:li:share:9999"},
                headers={"x-restli-id": "urn:li:share:9999"},
            )

        client = make_client(handler)
        try:
            post = await client.create_post(
                commentary="a take", asset_urn="urn:li:digitalmediaAsset:1"
            )
        finally:
            await client.aclose()

        assert post.post_urn == "urn:li:share:9999"
        assert seen["path"] == UGC_POSTS_PATH
        assert "a take" in seen["body"]

    async def test_http_errors_are_translated_with_a_scope_hint(self) -> None:
        client = make_client(
            lambda request: httpx.Response(403, text="Not enough permissions")
        )
        try:
            with pytest.raises(LinkedInAPIError) as excinfo:
                await client.create_post(commentary="a take")
        finally:
            await client.aclose()

        assert excinfo.value.status_code == 403
        assert "w_member_social" in str(excinfo.value)

    async def test_missing_person_urn_is_reported_clearly(self) -> None:
        client = LinkedInClient(
            "token",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        )
        try:
            with pytest.raises(LinkedInAPIError, match="person URN"):
                await client.register_upload()
        finally:
            await client.aclose()

    async def test_context_manager_closes_the_client(self) -> None:
        async with make_client(lambda request: httpx.Response(200, json={})) as client:
            assert isinstance(client, LinkedInClient)

    async def test_build_client_reads_credentials_from_config(self) -> None:
        from src.config import AppConfig, Secrets

        config = AppConfig(
            secrets=Secrets(
                linkedin_access_token="tok",  # type: ignore[arg-type]
                linkedin_person_urn="urn:li:person:5",
            )
        )
        client = build_client(config)
        try:
            assert client.access_token == "tok"
            assert client.person_urn == "urn:li:person:5"
        finally:
            await client.aclose()

    def test_build_client_requires_credentials(self) -> None:
        from src.config import AppConfig, ConfigurationError

        with pytest.raises(ConfigurationError):
            build_client(AppConfig())

    def test_register_path_constant_matches_the_api(self) -> None:
        assert REGISTER_UPLOAD_PATH == "/v2/assets?action=registerUpload"


# ---------------------------------------------------------------------------
# T022 — three-step asset workflow
# ---------------------------------------------------------------------------
class TestAssetPublisher:
    async def test_publish_runs_all_three_steps_in_order(
        self,
        tmp_path: Path,
    ) -> None:
        image = tmp_path / "card.png"
        image.write_bytes(make_png_bytes(16, 16))
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v2/assets":
                calls.append("register")
                return httpx.Response(200, json=REGISTER_RESPONSE)
            if request.method == "PUT":
                calls.append("upload")
                return httpx.Response(201)
            calls.append("post")
            return httpx.Response(201, json={"id": "urn:li:share:42"})

        client = make_client(handler)
        try:
            result = await LinkedInAssetPublisher(client).publish(
                commentary="a take", image_path=image
            )
        finally:
            await client.aclose()

        assert calls == ["register", "upload", "post"]
        assert result.post_urn == "urn:li:share:42"
        assert result.asset_urn == "urn:li:digitalmediaAsset:C5622AQH1234"

    async def test_publish_without_an_image_skips_the_upload(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(201, json={"id": "urn:li:share:1"})

        client = make_client(handler)
        try:
            result = await LinkedInAssetPublisher(client).publish(
                commentary="text only"
            )
        finally:
            await client.aclose()

        assert calls == [UGC_POSTS_PATH]
        assert result.asset_urn is None

    async def test_upload_image_returns_the_asset_urn(self, tmp_path: Path) -> None:
        image = tmp_path / "card.png"
        image.write_bytes(make_png_bytes(8, 8))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v2/assets":
                return httpx.Response(200, json=REGISTER_RESPONSE)
            return httpx.Response(201)

        client = make_client(handler)
        try:
            urn = await LinkedInAssetPublisher(client).upload_image(image)
        finally:
            await client.aclose()

        assert urn == "urn:li:digitalmediaAsset:C5622AQH1234"

    async def test_publish_image_post_convenience_helper(self, tmp_path: Path) -> None:
        image = tmp_path / "card.png"
        image.write_bytes(make_png_bytes(8, 8))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v2/assets":
                return httpx.Response(200, json=REGISTER_RESPONSE)
            if request.method == "PUT":
                return httpx.Response(201)
            return httpx.Response(201, json={"id": "urn:li:share:7"})

        client = make_client(handler)
        try:
            result = await publish_image_post(
                client, commentary="hello", image_path=image
            )
        finally:
            await client.aclose()

        assert result.post_urn == "urn:li:share:7"
