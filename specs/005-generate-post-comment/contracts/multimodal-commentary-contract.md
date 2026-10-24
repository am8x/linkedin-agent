# Interface Contract: Multimodal Post Comment Synthesis

**Branch**: `005-generate-post-comment` | **Date**: 2026-10-22 | **Spec**: [spec.md](../spec.md)

This contract defines the multimodal input schema, system context embedding, prompt template, and output constraints for synthesizing persona-aligned LinkedIn comments.

---

## 1. Input Schema

```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class MultimodalCommentInput:
    """Input parameters for synthesizing a targeted post comment."""
    post_text: str
    author_name: str
    post_urn: str
    image_bytes: bytes | None = None
    image_mime_type: str = "image/jpeg"
    system_instruction: str = ""
```

---

## 2. Gemini Multimodal Call Structure

Using the official Google GenAI SDK (`google-genai`):

```python
from google import genai
from google.genai import types

async def generate_multimodal_comment(
    client: genai.Client,
    model: str,
    payload: MultimodalCommentInput,
) -> str:
    parts = []
    
    # 1. Add visual part if image bytes exist
    if payload.image_bytes:
        parts.append(
            types.Part.from_bytes(
                data=payload.image_bytes,
                mime_type=payload.image_mime_type,
            )
        )
    
    # 2. Add textual analysis prompt
    parts.append(
        types.Part.from_text(
            f"Analyze this LinkedIn post by {payload.author_name} and any attached visual graphic/diagram.\n"
            f"Post copy:\n{payload.post_text}\n\n"
            f"Write a sharp, high-signal technical comment directly reacting to the engineering trade-off or core insight."
        )
    )

    response = await client.aio.models.generate_content(
        model=model,
        contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(
            system_instruction=payload.system_instruction,
            temperature=0.7,
            max_output_tokens=300,
        ),
    )
    return response.text or ""
```

---

## 3. Strict Stylometric Prompt Directives

The system instruction injected into the Gemini call embeds the **Amit Kumar** persona with comment-specific constraints:

1. **Length & Density**: Exactly 1 paragraph. 2–3 blunt sentences. Strict ceiling: **<250 characters**.
2. **Cognitive Move**: Execute a premise-audit reframe or bottleneck drill. State the physical, algorithmic, or operational constraint directly.
3. **Voice & Rhythm**:
   - Alternating cadence (a 3–6 word blunt punchline paired with a medium analytical sentence).
   - Conversational contractions (*it's*, *doesn't*, *don't*, *can't*).
   - Direct address to the practitioner (*you*, *your*).
4. **Prohibitions**:
   - 0 emojis.
   - 0 hashtags.
   - 0 participial openers (`-ing` sentence starters).
   - 0 AI clichés (*delve*, *testament*, *tapestry*, *revolutionize*, *game-changer*).
   - No generic praise or corporate cheerleading (*"Great post!"*, *"Thanks for sharing"*).
