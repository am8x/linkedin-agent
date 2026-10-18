# Contract: LinkedIn Comments API & Fallback Delivery

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Status**: Ratified  
**Version**: 1.0.0  

---

## 1. Endpoint Protocol

Creates a comment on an existing LinkedIn post URN (e.g., `urn:li:ugcPost:12345` or `urn:li:share:12345`) to place the source article link in the first comment for reach optimization.

- **Method**: `POST`
- **URL**: `https://api.linkedin.com/v2/socialActions/{postUrn}/comments`
- **Headers**:
  ```http
  Authorization: Bearer {LINKEDIN_ACCESS_TOKEN}
  X-Restli-Protocol-Version: 2.0.0
  LinkedIn-Version: 202411
  Content-Type: application/json
  ```
- **Payload**:
  ```json
  {
    "actor": "{PERSON_URN}",
    "message": {
      "text": "Source article ({publication_name}): {canonical_url}"
    }
  }
  ```

---

## 2. Response Handling & Status Codes

- **HTTP 201 Created**:
  - Response contains `id` header or body (e.g. `urn:li:comment:(ugcPost:12345,67890)`).
  - Recorded in publication ledger: `first_comment_status = 'POSTED_API'`, `first_comment_urn = '...'`.
- **HTTP 401 / 403 Forbidden** (e.g. token lacks Community Management / comment scope):
  - Handled cleanly as non-fatal.
  - Recorded in publication ledger: `first_comment_status = 'STAGED_MANUAL'`.
  - Terminal output and logs display:
    ```text
    [LinkedIn] Main post published successfully: urn:li:ugcPost:...
    [LinkedIn] Automated comment unavailable (insufficient API permissions).
    [Action Required] Copy & paste this first comment to maximize post reach:
    --------------------------------------------------------------------------
    Source article (Ars Technica): https://arstechnica.com/...
    --------------------------------------------------------------------------
    ```
- **Network / Timeout Error**:
  - Main post remains published; comment failure does not roll back or raise fatal exception.
  - Status recorded as `STAGED_MANUAL`.
