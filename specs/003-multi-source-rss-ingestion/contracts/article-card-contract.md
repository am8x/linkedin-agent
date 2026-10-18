# Contract: News Card HTML/CSS Layout & Playwright Capture

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Status**: Ratified  
**Version**: 1.0.0  

---

## 1. Overview

Defines the self-contained HTML/CSS template rendered by Playwright to generate the visual LinkedIn news card PNG asset.

---

## 2. Template Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #000000;
      color: #ffffff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 1200px;
      height: 800px;
      overflow: hidden;
    }
    .card {
      width: 1040px;
      background: #16181c;
      border: 1px solid #2f3336;
      border-radius: 16px;
      padding: 40px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: #71767b;
      font-size: 18px;
    }
    .source-badge {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 600;
      color: #e7e9ea;
    }
    .headline {
      font-size: 32px;
      font-weight: 700;
      line-height: 1.3;
      color: #ffffff;
    }
    .media-container {
      width: 100%;
      height: 380px;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #2f3336;
      background: #000000;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .media-container img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    /* Typography fallback when no image exists */
    .card.no-image {
      padding: 60px 48px;
    }
    .card.no-image .headline {
      font-size: 40px;
      line-height: 1.35;
    }
    .card.no-image .summary-excerpt {
      font-size: 22px;
      line-height: 1.5;
      color: #a0a6ad;
      margin-top: 16px;
    }
  </style>
</head>
<body>
  <div class="card {{ layout_class }}">
    <div class="header">
      <div class="source-badge">
        <span>{{ publication_name }}</span>
        <span>•</span>
        <span style="color: #71767b;">{{ domain }}</span>
      </div>
      <div class="date">{{ formatted_date }}</div>
    </div>
    <div class="headline">{{ headline }}</div>
    {% if has_image %}
    <div class="media-container">
      <img src="{{ image_uri }}" alt="Article Lead Image" />
    </div>
    {% else %}
    <div class="summary-excerpt">{{ summary_excerpt }}</div>
    {% endif %}
  </div>
</body>
</html>
```

---

## 3. Render Invariants

1. **Retina Capture**: Viewport set to 1200 x 800 with `device_scale_factor: 2.0`, generating a crisp 2400 x 1600 physical PNG.
2. **Zero External Font/Asset HTTP Requests**: Template uses system typography stacks. Images are loaded via local `file://` URIs or data URIs to guarantee sub-300ms deterministic rendering.
3. **Graceful Fallback**: If `has_image` is false or image fails to load, `layout_class` switches to `no-image`, triggering the expanded typography layout.
