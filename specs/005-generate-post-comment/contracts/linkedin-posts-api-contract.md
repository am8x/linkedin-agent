# Interface Contract: LinkedIn REST API Post & Comment Protocol

**Branch**: `005-generate-post-comment` | **Date**: 2026-10-22 | **Spec**: [spec.md](../spec.md)

This contract defines the low-level HTTP requests, protocol headers, payload structures, and error translation for retrieving target posts and creating comments on LinkedIn.

---

## 1. Get Post Details (`GET /rest/posts/{encodedUrn}`)

### Request
```http
GET /rest/posts/{encodedUrn} HTTP/1.1
Host: api.linkedin.com
Authorization: Bearer {LINKEDIN_ACCESS_TOKEN}
LinkedIn-Version: 202411
X-Restli-Protocol-Version: 2.0.0
Accept: application/json
```

- Path parameter `encodedUrn`: URL-encoded string of the target post URN (e.g. `urn%3Ali%3Aactivity%3A7518646093870510081` or `urn%3Ali%3AugcPost%3A7518646093870510081`).

### Success Response (`200 OK`)
```json
{
  "id": "urn:li:activity:7518646093870510081",
  "author": "urn:li:organization:123456",
  "commentary": "Here is our latest technical benchmark comparing model architectures...",
  "content": {
    "media": {
      "id": "urn:li:digitalmediaAsset:D5605AQE123...",
      "title": "architecture_diagram.png"
    }
  },
  "lifecycleState": "PUBLISHED",
  "visibility": "PUBLIC"
}
```

### Error Responses
- `401 Unauthorized`: Token invalid or expired. Raises `LinkedInAPIError("LinkedIn access token expired or invalid", status_code=401)`.
- `403 Forbidden`: Insufficient scope (requires `r_basicprofile`, `r_member_social`, or partner permissions). Raises `LinkedInAPIError`.
- `404 Not Found`: Post does not exist or URN format is unmapped. Raises `LinkedInAPIError("LinkedIn post not found", status_code=404)`.

---

## 2. Create Comment (`POST /v2/socialActions/{encodedUrn}/comments`)

### Request
```http
POST /v2/socialActions/{encodedUrn}/comments HTTP/1.1
Host: api.linkedin.com
Authorization: Bearer {LINKEDIN_ACCESS_TOKEN}
LinkedIn-Version: 202411
X-Restli-Protocol-Version: 2.0.0
Content-Type: application/json

{
  "actor": "urn:li:person:8675309",
  "message": {
    "text": "Hybrid reasoning shifts the bottleneck from token volume to early-exit policy tuning. You either train the router in the weights or pay a 2x latency tax."
  }
}
```

### Success Response (`201 Created`)
```json
{
  "actor": "urn:li:person:8675309",
  "created": {
    "time": 1729579200000
  },
  "id": "urn:li:comment:(activity:7518646093870510081,123456789)",
  "message": {
    "text": "Hybrid reasoning shifts the bottleneck..."
  }
}
```
Header: `x-restli-id: urn:li:comment:(activity:7518646093870510081,123456789)`

---

## 3. Client Method Signatures (`src/linkedin/client.py`)

```python
async def get_post(self, post_urn: str) -> LinkedInPostDetails:
    """Retrieve post commentary text and media metadata from LinkedIn REST API."""
    ...

async def create_comment(
    self,
    post_urn: str,
    text: str,
    *,
    actor: str | None = None,
) -> CreateCommentResponse:
    """Publish a comment to an existing post via the socialActions endpoint."""
    ...
```
