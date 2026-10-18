"""LinkedIn REST v2 request/response payloads plus the publication domain model.

The three-step official publishing protocol is:

1. ``POST /v2/assets?action=registerUpload`` → digital-media asset URN + upload URL
2. ``PUT  <uploadUrl>``                     → binary image payload
3. ``POST /v2/ugcPosts``                   → the share itself

Only :mod:`src.linkedin.client` performs I/O; this module is pure schema.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RECIPE_FEEDSHARE_IMAGE = "urn:li:digitalmediaRecipe:feedshare-image"
SERVICE_RELATIONSHIP_IDENTIFIER = "urn:li:userGeneratedContent"
SUPPORTED_UPLOAD_MECHANISM = "SYNCHRONOUS_UPLOAD"
UPLOAD_MECHANISM_RESPONSE_KEY = (
    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
)
UGC_SHARE_CONTENT_KEY = "com.linkedin.ugc.ShareContent"
UGC_VISIBILITY_KEY = "com.linkedin.ugc.MemberNetworkVisibility"
LIFECYCLE_PUBLISHED = "PUBLISHED"

PublicationStatus = Literal["PUBLISHED", "SKIPPED", "DRY_RUN", "FAILED"]

URN_PREFIXES: dict[str, tuple[str, ...]] = {
    "post": ("urn:li:share:", "urn:li:ugcPost:"),
    "asset": ("urn:li:digitalmediaAsset:",),
}


class LinkedInAPIError(RuntimeError):
    """Raised when the LinkedIn REST API returns an error response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Step 1 — register an upload
# ---------------------------------------------------------------------------
class RegisterUploadRequest(BaseModel):
    """``POST /v2/assets?action=registerUpload`` request body."""

    model_config = ConfigDict(extra="ignore")

    owner: str = Field(description="Person URN, e.g. urn:li:person:8675309")
    recipe: str = RECIPE_FEEDSHARE_IMAGE
    service_relationship: str = SERVICE_RELATIONSHIP_IDENTIFIER
    upload_mechanism: str = SUPPORTED_UPLOAD_MECHANISM

    @classmethod
    def for_person(cls, person_urn: str) -> RegisterUploadRequest:
        return cls(owner=ensure_person_urn(person_urn))

    def to_payload(self) -> dict[str, Any]:
        return {
            "registerUploadRequest": {
                "recipes": [self.recipe],
                "owner": self.owner,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": self.service_relationship,
                    }
                ],
                "supportedUploadMechanism": [self.upload_mechanism],
            }
        }


class RegisterUploadResponse(BaseModel):
    """Parsed ``registerUpload`` response."""

    model_config = ConfigDict(extra="ignore")

    asset_urn: str
    upload_url: str
    upload_mechanism: str = UPLOAD_MECHANISM_RESPONSE_KEY
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("asset_urn")
    @classmethod
    def _validate_asset_urn(cls, value: str) -> str:
        if not value.startswith(URN_PREFIXES["asset"]):
            raise ValueError(f"unexpected digital-media asset URN: {value!r}")
        return value

    @field_validator("upload_url")
    @classmethod
    def _validate_upload_url(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError(f"upload URL must be https: {value!r}")
        return value

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RegisterUploadResponse:
        """Parse LinkedIn's deeply nested ``registerUpload`` response."""
        value = payload.get("value", payload) or {}
        mechanism = value.get("uploadMechanism", {}) or {}
        upload_request = mechanism.get(UPLOAD_MECHANISM_RESPONSE_KEY, {}) or {}

        asset_urn = value.get("asset") or value.get("assetUrn") or ""
        upload_url = upload_request.get("uploadUrl") or value.get("uploadUrl") or ""
        if not asset_urn or not upload_url:
            raise LinkedInAPIError(
                "registerUpload response is missing the asset URN or upload URL: "
                f"{payload!r}",
            )
        return cls(
            asset_urn=str(asset_urn),
            upload_url=str(upload_url),
            upload_mechanism=str(next(iter(mechanism), UPLOAD_MECHANISM_RESPONSE_KEY)),
            raw=payload if isinstance(payload, dict) else {},
        )


# ---------------------------------------------------------------------------
# Step 3 — create the UGC post
# ---------------------------------------------------------------------------
class ShareContent(BaseModel):
    """The ``com.linkedin.ugc.ShareContent`` block."""

    model_config = ConfigDict(extra="ignore")

    commentary: str
    share_media_category: str = "IMAGE"
    media_urn: str | None = None
    media_title: str | None = None

    def to_payload(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "shareCommentary": {"text": self.commentary},
            "shareMediaCategory": self.share_media_category,
        }
        if self.media_urn:
            media: dict[str, Any] = {
                "status": "READY",
                "media": self.media_urn,
            }
            if self.media_title:
                media["title"] = {"text": self.media_title}
            value["media"] = [media]
        return value


class UgcPostRequest(BaseModel):
    """``POST /v2/ugcPosts`` request body."""

    model_config = ConfigDict(extra="ignore")

    author: str
    commentary: str
    media_urn: str | None = None
    media_title: str | None = None
    visibility: str = "PUBLIC"
    lifecycle_state: str = LIFECYCLE_PUBLISHED

    @field_validator("commentary")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("commentary must not be empty")
        return value

    def to_payload(self) -> dict[str, Any]:
        return {
            "author": ensure_person_urn(self.author),
            "lifecycleState": self.lifecycle_state,
            "specificContent": {
                UGC_SHARE_CONTENT_KEY: ShareContent(
                    commentary=self.commentary,
                    media_urn=self.media_urn,
                    media_title=self.media_title,
                ).to_payload()
            },
            "visibility": {
                UGC_VISIBILITY_KEY: self.visibility,
            },
        }


class UgcPostResponse(BaseModel):
    """Parsed ``ugcPosts`` creation response."""

    model_config = ConfigDict(extra="ignore")

    post_urn: str
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        response_headers: dict[str, str] | None = None,
    ) -> UgcPostResponse:
        """Parse the post URN from the body or the ``x-restli-id`` header."""
        headers = {k.lower(): v for k, v in (response_headers or {}).items()}
        urn = payload.get("id") or payload.get("urn") or headers.get("x-restli-id", "")
        if not urn:
            raise LinkedInAPIError(
                "ugcPosts response did not include a post URN: "
                f"{payload!r} headers={response_headers!r}",
            )
        return cls(post_urn=str(urn), raw=payload if isinstance(payload, dict) else {})


class LinkedInPostResult(BaseModel):
    """Successful outcome of the full three-step publish."""

    model_config = ConfigDict(extra="ignore")

    post_urn: str
    asset_urn: str | None = None
    commentary: str = ""
    media_category: str = "IMAGE"

    def to_publication_record(
        self,
        *,
        tweet_id: str,
        author_handle: str,
        published_at: datetime | None = None,
    ) -> PublicationRecord:
        return PublicationRecord(
            tweet_id=tweet_id,
            author_handle=author_handle,
            linkedin_post_urn=self.post_urn,
            linkedin_asset_urn=self.asset_urn,
            status="PUBLISHED",
            commentary_text=self.commentary,
            published_at=published_at or datetime.now(UTC),
        )


# ---------------------------------------------------------------------------
# Domain entity
# ---------------------------------------------------------------------------
class PublicationRecord(BaseModel):
    """Completed or skipped publication transaction (per ``data-model.md``)."""

    model_config = ConfigDict(extra="ignore")

    tweet_id: str = Field(min_length=1)
    author_handle: str = Field(min_length=1)
    linkedin_post_urn: str | None = None
    linkedin_asset_urn: str | None = None
    status: PublicationStatus
    commentary_text: str = ""
    published_at: datetime | None = None
    error_message: str | None = None

    @field_validator("published_at")
    @classmethod
    def _normalise_published_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def succeeded(self) -> bool:
        return self.status == "PUBLISHED"


# ---------------------------------------------------------------------------
# First comment — socialActions API
# ---------------------------------------------------------------------------
class CreateCommentRequest(BaseModel):
    """Payload for POST /v2/socialActions/{postUrn}/comments."""

    model_config = ConfigDict(extra="ignore")

    actor: str = Field(description="Person URN, e.g. urn:li:person:8675309")
    message: str = Field(description="Comment body text")

    def to_payload(self) -> dict[str, Any]:
        return {
            "actor": ensure_person_urn(self.actor),
            "message": {
                "text": self.message,
            },
        }


class CreateCommentResponse(BaseModel):
    """Parsed response from creating a comment."""

    model_config = ConfigDict(extra="ignore")

    comment_urn: str
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def parse(
        cls,
        payload: dict[str, Any],
        *,
        response_headers: dict[str, str] | None = None,
    ) -> CreateCommentResponse:
        headers = {k.lower(): v for k, v in (response_headers or {}).items()}
        urn = (
            payload.get("id")
            or payload.get("urn")
            or headers.get("x-restli-id", "")
        )
        return cls(comment_urn=str(urn), raw=payload if isinstance(payload, dict) else {})


def ensure_person_urn(value: str) -> str:
    """Normalise a bare member id or person URN into ``urn:li:person:<id>``."""
    cleaned = value.strip()
    if cleaned.startswith("urn:li:person:"):
        return cleaned
    if cleaned.startswith("urn:li:"):
        return cleaned
    return f"urn:li:person:{cleaned.lstrip(':')}"


__all__ = [
    "CreateCommentRequest",
    "CreateCommentResponse",
    "LIFECYCLE_PUBLISHED",
    "LinkedInAPIError",
    "LinkedInPostResult",
    "PublicationRecord",
    "PublicationStatus",
    "RECIPE_FEEDSHARE_IMAGE",
    "RegisterUploadRequest",
    "RegisterUploadResponse",
    "SERVICE_RELATIONSHIP_IDENTIFIER",
    "SUPPORTED_UPLOAD_MECHANISM",
    "ShareContent",
    "UGC_SHARE_CONTENT_KEY",
    "UGC_VISIBILITY_KEY",
    "UPLOAD_MECHANISM_RESPONSE_KEY",
    "UgcPostRequest",
    "UgcPostResponse",
    "ensure_person_urn",
]
