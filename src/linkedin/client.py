"""Low-level LinkedIn REST v2 HTTP client (async, httpx-backed).

This module owns OAuth headers, error translation, and the three protocol
calls.  Higher-level publish orchestration lives in
:mod:`src.linkedin.assets`.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

from src.linkedin.models import (
    CreateCommentRequest,
    CreateCommentResponse,
    LinkedInAPIError,
    RegisterUploadRequest,
    RegisterUploadResponse,
    UgcPostRequest,
    UgcPostResponse,
    ensure_person_urn,
)
from src.logging import get_logger

logger = get_logger(__name__)

DEFAULT_API_BASE = "https://api.linkedin.com"
REGISTER_UPLOAD_PATH = "/v2/assets?action=registerUpload"
UGC_POSTS_PATH = "/v2/ugcPosts"

# LinkedIn requires an explicit API version header; this stays on a stable,
# documented version rather than "latest".
DEFAULT_LINKEDIN_VERSION = "202411"
DEFAULT_TIMEOUT_SECONDS = 60.0


class LinkedInClient:
    """Async client for the officially supported LinkedIn UGC publishing API."""

    def __init__(
        self,
        access_token: str,
        *,
        person_urn: str | None = None,
        api_base: str = DEFAULT_API_BASE,
        api_version: str = DEFAULT_LINKEDIN_VERSION,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not access_token:
            raise LinkedInAPIError("A LinkedIn access token is required.")
        self.access_token = access_token
        self.person_urn = ensure_person_urn(person_urn) if person_urn else None
        self.api_base = api_base.rstrip("/")
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=self.api_base,
            timeout=timeout_seconds,
            transport=transport,
            headers=self.default_headers(),
        )
        if http_client is not None:
            for key, value in self.default_headers().items():
                http_client.headers.setdefault(key, value)

    # -- lifecycle ----------------------------------------------------------
    def default_headers(self) -> dict[str, str]:
        """OAuth + protocol headers required by every LinkedIn REST v2 call."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
            "Content-Type": "application/json",
        }

    async def __aenter__(self) -> LinkedInClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client when this instance owns it."""
        if self._owns_client:
            await self._client.aclose()

    # -- error handling -----------------------------------------------------
    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        snippet = ""
        try:
            snippet = response.text[:500]
        except Exception:  # pragma: no cover - defensive
            snippet = "<unreadable body>"
        hint = ""
        if response.status_code in (401, 403):
            hint = " Check LINKEDIN_ACCESS_TOKEN and the w_member_social scope."
        raise LinkedInAPIError(
            f"LinkedIn {operation} failed with HTTP {response.status_code}: "
            f"{snippet}{hint}",
            status_code=response.status_code,
        )

    # -- step 1: register the upload ----------------------------------------
    async def register_upload(
        self,
        *,
        owner: str | None = None,
    ) -> RegisterUploadResponse:
        """Reserve a digital-media asset and obtain its upload URL."""
        request = RegisterUploadRequest.for_person(
            owner or self.person_urn or self._require_person_urn()
        )
        logger.debug("Registering LinkedIn image upload for %s", request.owner)

        response = await self._client.post(
            REGISTER_UPLOAD_PATH,
            json=request.to_payload(),
            headers=self.default_headers(),
        )
        self._raise_for_status(response, "registerUpload")

        payload = self._safe_json(response)
        parsed = RegisterUploadResponse.from_payload(payload)
        logger.debug("Registered asset %s", parsed.asset_urn)
        return parsed

    # -- step 2: upload the binary -----------------------------------------
    async def upload_binary(
        self,
        upload_url: str,
        file_path: str | Path,
        *,
        content_type: str = "image/png",
    ) -> None:
        """``PUT`` the image bytes to the URL returned by ``registerUpload``."""
        path = Path(file_path)
        if not path.exists():
            raise LinkedInAPIError(f"Image to upload does not exist: {path}")

        data = path.read_bytes()
        logger.debug("Uploading %d bytes of image data to LinkedIn", len(data))

        response = await self._client.put(
            upload_url,
            content=data,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": content_type,
            },
        )
        self._raise_for_status(response, "binary upload")

    # -- step 3: create the UGC post ---------------------------------------
    async def create_post(
        self,
        *,
        commentary: str,
        asset_urn: str | None = None,
        title: str | None = None,
        author: str | None = None,
        visibility: str = "PUBLIC",
    ) -> UgcPostResponse:
        """Create the share (with an optional image) and return its URN."""
        request = UgcPostRequest(
            author=author or self.person_urn or self._require_person_urn(),
            commentary=commentary,
            media_urn=asset_urn,
            media_title=title,
            visibility=visibility,
        )
        response = await self._client.post(
            UGC_POSTS_PATH,
            json=request.to_payload(),
            headers=self.default_headers(),
        )
        self._raise_for_status(response, "ugcPosts")

        payload = self._safe_json(response)
        parsed = UgcPostResponse.from_payload(
            payload,
            response_headers=dict(response.headers),
        )
        logger.info("Created LinkedIn post %s", parsed.post_urn)
        return parsed

    # -- step 4: create first comment --------------------------------------
    async def create_comment(
        self,
        post_urn: str,
        text: str,
        *,
        actor: str | None = None,
    ) -> CreateCommentResponse:
        """Post a comment on an existing LinkedIn share or UGC post."""
        clean_actor = actor or self.person_urn or self._require_person_urn()
        request = CreateCommentRequest(
            actor=clean_actor,
            message=text,
        )
        encoded_urn = urllib.parse.quote(urllib.parse.unquote(post_urn), safe="")
        url_path = f"/v2/socialActions/{encoded_urn}/comments"
        response = await self._client.post(
            url_path,
            json=request.to_payload(),
            headers=self.default_headers(),
        )
        self._raise_for_status(response, "socialActions comments")

        payload = self._safe_json(response)
        parsed = CreateCommentResponse.parse(
            payload,
            response_headers=dict(response.headers),
        )
        logger.info("Created LinkedIn comment %s on %s", parsed.comment_urn, post_urn)
        return parsed

    # -- helpers ------------------------------------------------------------
    def _require_person_urn(self) -> str:
        raise LinkedInAPIError(
            "No LinkedIn person URN configured. Set LINKEDIN_PERSON_URN or pass "
            "one explicitly.",
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - defensive
            return {}
        return payload if isinstance(payload, dict) else {"value": payload}


def build_client(config: Any) -> LinkedInClient:
    """Construct a client from an :class:`src.config.AppConfig` instance."""
    access_token, person_urn = config.require_linkedin_credentials()
    return LinkedInClient(access_token, person_urn=person_urn)


__all__ = [
    "DEFAULT_API_BASE",
    "DEFAULT_LINKEDIN_VERSION",
    "DEFAULT_TIMEOUT_SECONDS",
    "REGISTER_UPLOAD_PATH",
    "UGC_POSTS_PATH",
    "LinkedInClient",
    "build_client",
]
