"""Low-level LinkedIn REST v2 HTTP client (async, httpx-backed).

This module owns OAuth headers, error translation, and the three protocol
calls.  Higher-level publish orchestration lives in
:mod:`src.linkedin.assets`.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

from src.linkedin.models import (
    CreateCommentRequest,
    CreateCommentResponse,
    LinkedInAPIError,
    LinkedInMediaAsset,
    LinkedInPostDetails,
    RegisterUploadRequest,
    RegisterUploadResponse,
    UgcPostRequest,
    UgcPostResponse,
    ensure_person_urn,
    parse_linkedin_post_target,
)
from src.logging import get_logger

logger = get_logger(__name__)

DEFAULT_API_BASE = "https://api.linkedin.com"
REGISTER_UPLOAD_PATH = "/v2/assets?action=registerUpload"
UGC_POSTS_PATH = "/v2/ugcPosts"

# LinkedIn requires an explicit API version header; this stays on a stable,
# documented version rather than "latest".
DEFAULT_LINKEDIN_VERSION = "202511"
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
        if response.status_code == 400:
            match = re.search(r"actual threadUrn:\s*(urn:li:[^\s\"\'\\]+)", response.text)
            if match:
                actual_urn = match.group(1).rstrip(",.")
                logger.info(
                    "Retrying comment creation with canonical threadUrn: %s", actual_urn
                )
                return await self.create_comment(actual_urn, text, actor=actor)

        self._raise_for_status(response, "socialActions comments")

        payload = self._safe_json(response)
        parsed = CreateCommentResponse.parse(
            payload,
            response_headers=dict(response.headers),
        )
        logger.info("Created LinkedIn comment %s on %s", parsed.comment_urn, post_urn)
        return parsed

    # -- step 5: ingest target post & media --------------------------------
    async def get_post(self, post_urn: str) -> LinkedInPostDetails:
        """Retrieve post commentary text and media metadata from LinkedIn REST API."""
        target_urn = parse_linkedin_post_target(post_urn)
        numeric_id = target_urn.split(":")[-1]

        candidates = [target_urn]
        if target_urn.startswith("urn:li:activity:"):
            candidates.extend(
                [f"urn:li:ugcPost:{numeric_id}", f"urn:li:share:{numeric_id}"]
            )
        elif target_urn.startswith("urn:li:ugcPost:"):
            candidates.extend(
                [f"urn:li:activity:{numeric_id}", f"urn:li:share:{numeric_id}"]
            )

        last_response: httpx.Response | None = None
        for candidate_urn in candidates:
            encoded_urn = urllib.parse.quote(candidate_urn, safe="")
            url_path = f"/rest/posts/{encoded_urn}"
            logger.debug("Querying LinkedIn post endpoint: %s", url_path)
            response = await self._client.get(url_path, headers=self.default_headers())
            last_response = response
            if response.status_code in (403, 404):
                continue
            self._raise_for_status(response, "get_post")
            payload = self._safe_json(response)
            return self._parse_post_details(payload, default_urn=candidate_urn)

        if last_response is not None and last_response.status_code in (403, 404):
            try:
                return await self._fetch_public_post_details(post_urn, target_urn)
            except Exception as fallback_exc:
                logger.debug(
                    "Public web fallback failed after %s: %s",
                    last_response.status_code,
                    fallback_exc,
                )
                self._raise_for_status(last_response, "get_post")

        if last_response is not None:
            self._raise_for_status(last_response, "get_post")
        raise LinkedInAPIError(f"LinkedIn post not found: {post_urn}", status_code=404)

    async def _fetch_public_post_details(
        self, original_target: str, canonical_urn: str
    ) -> LinkedInPostDetails:
        """Fallback to fetch public post metadata from web page when REST API returns 403/404."""

        url = (
            original_target
            if original_target.startswith("http")
            else f"https://www.linkedin.com/feed/update/{canonical_urn}/"
        )
        logger.info("Attempting public web extraction fallback for %s", url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
        }
        resp = await self._client.get(url, headers=headers)
        if not resp.is_success:
            raise LinkedInAPIError(
                f"Public post fetch failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        text = resp.text

        m_desc = re.search(
            r'<meta\s+(?:property="og:description"|name="description")\s+content="([^"]*)"',
            text,
        )
        if not m_desc:
            m_desc = re.search(
                r'<meta\s+name="twitter:description"\s+content="([^"]*)"', text
            )
        commentary = (
            html.unescape(m_desc.group(1)).replace("\ufffd", "'").strip()
            if m_desc
            else ""
        )
        commentary = re.sub(
            r"\s*\|\s*\d+\s+comments\s+on\s+LinkedIn\s*$",
            "",
            commentary,
            flags=re.IGNORECASE,
        ).strip()

        m_title = re.search(
            r'<meta\s+(?:property="og:title"|name="twitter:title")\s+content="([^"]*)"',
            text,
        )
        title_str = html.unescape(m_title.group(1)).strip() if m_title else ""
        author_name = ""
        if "|" in title_str:
            parts = [p.strip() for p in title_str.split("|")]
            for p in parts:
                if not p.startswith("#") and "comment" not in p.lower():
                    author_name = p
                    break
        if not author_name:
            author_name = title_str

        m_img = re.search(
            r'<meta\s+(?:property="og:image"|name="twitter:image")\s+content="([^"]*)"',
            text,
        )
        image_url = html.unescape(m_img.group(1)).strip() if m_img else None

        media = LinkedInMediaAsset(
            media_url=image_url,
            media_type="IMAGE" if image_url else "NONE",
        )

        m_ugc = re.search(r"(urn:li:ugcPost:\d+)", text)
        resolved_post_urn = m_ugc.group(1) if m_ugc else canonical_urn

        return LinkedInPostDetails(
            post_urn=resolved_post_urn,
            author_urn=canonical_urn,
            author_name=author_name,
            commentary_text=commentary,
            media=media,
            raw_payload={"fallback": "public_html", "title": title_str},
        )

    def _parse_post_details(
        self, payload: dict[str, Any], *, default_urn: str
    ) -> LinkedInPostDetails:
        post_urn = str(payload.get("id") or payload.get("urn") or default_urn)
        author_urn = str(payload.get("author") or "")
        author_name = str(payload.get("authorName") or payload.get("author_name") or "")
        commentary = str(payload.get("commentary") or "")

        media = LinkedInMediaAsset()
        content = payload.get("content")
        if isinstance(content, dict):
            media_info = content.get("media")
            if isinstance(media_info, dict):
                asset_urn = media_info.get("id") or media_info.get("asset")
                media_url = media_info.get("downloadUrl") or media_info.get("url")
                title = media_info.get("title")
                media_type = (
                    "IMAGE"
                    if (asset_urn or media_url or "image" in str(media_info).lower())
                    else "NONE"
                )
                media = LinkedInMediaAsset(
                    asset_urn=str(asset_urn) if asset_urn else None,
                    media_url=str(media_url) if media_url else None,
                    title=str(title) if title else None,
                    media_type=media_type,
                )

        return LinkedInPostDetails(
            post_urn=post_urn,
            author_urn=author_urn,
            author_name=author_name,
            commentary_text=commentary,
            media=media,
            raw_payload=payload,
        )

    async def fetch_image_bytes(self, image_url: str) -> tuple[bytes, str]:
        """Download binary image content and detect its mime type."""
        try:
            response = await self._client.get(image_url)
        except Exception as exc:
            raise LinkedInAPIError(
                f"Failed to fetch image bytes from {image_url}: {exc}"
            ) from exc
        if not response.is_success:
            raise LinkedInAPIError(
                f"Failed to fetch image bytes: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        content_type = (
            response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        )
        return response.content, content_type

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
