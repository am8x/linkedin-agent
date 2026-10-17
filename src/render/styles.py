"""Card styling: dark-theme enforcement and engagement-metric suppression.

The stylesheet and DOM script generated here are injected into the tweet
permalink page before capture so the resulting screenshot is a clean,
distraction-free quote card rather than a full Twitter UI dump.
"""

from __future__ import annotations

from typing import Any, Literal

Theme = Literal["dark", "light"]

TWEET_CARD_SELECTOR = 'article[data-testid="tweet"]'

DEFAULT_VIEWPORT_WIDTH = 1200
DEFAULT_VIEWPORT_HEIGHT = 800

# Engagement counters and interaction chrome that must never appear on the card.
METRIC_SELECTORS: tuple[str, ...] = (
    '[role="group"]',  # reply / retweet / like / view / bookmark cluster
    '[data-testid="reply"]',
    '[data-testid="retweet"]',
    '[data-testid="unretweet"]',
    '[data-testid="like"]',
    '[data-testid="unlike"]',
    '[data-testid="bookmark"]',
    '[data-testid="removeBookmark"]',
    '[data-testid="app-text-transition-container"]',
    '[data-testid="analytics"]',
    'a[href$="/analytics"]',
    '[aria-label*="View post analytics"]',
    '[aria-label*="Likes"]',
    '[aria-label*="Reposts"]',
    '[aria-label*="Replies"]',
)

# Surrounding page furniture removed from the full-page screenshot fallback.
# X nests the tweet article inside `[data-testid="primaryColumn"]`'s first child,
# so that node must never be hidden here — it would hide the card itself.
CHROME_SELECTORS: tuple[str, ...] = (
    'header[role="banner"]',
    '[data-testid="sidebarColumn"]',
    '[data-testid="BottomBar"]',
    '[data-testid="DMDrawer"]',
    'nav[aria-label="Primary"]',
)

DARK_THEME_CSS = """
html, body {
    color-scheme: dark !important;
    background-color: #000000 !important;
}
body { background: #000000 !important; }
article[data-testid="tweet"],
article[data-testid="tweet"] > div {
    background-color: #000000 !important;
    border-color: #2f3336 !important;
}
article[data-testid="tweet"] a,
article[data-testid="tweet"] span {
    color: #e7e9ea;
}
article[data-testid="tweet"] [data-testid="User-Name"] span,
article[data-testid="tweet"] a[href*="/status/"] span {
    color: #e7e9ea !important;
}
"""

LIGHT_THEME_CSS = """
html, body {
    color-scheme: light !important;
    background-color: #ffffff !important;
}
article[data-testid="tweet"],
article[data-testid="tweet"] > div {
    background-color: #ffffff !important;
}
"""

THEME_CSS: dict[str, str] = {"dark": DARK_THEME_CSS, "light": LIGHT_THEME_CSS}


def _selector_list(selectors: tuple[str, ...]) -> str:
    return ", ".join(selectors)


def build_metric_suppression_css(selectors: tuple[str, ...] = METRIC_SELECTORS) -> str:
    """Return CSS that hides every engagement counter on the card."""
    if not selectors:
        return ""
    return (
        f"{_selector_list(selectors)} {{\n"
        "    display: none !important;\n"
        "    visibility: hidden !important;\n"
        "}\n"
    )


def build_card_css(
    *,
    theme: Theme = "dark",
    hide_metrics: bool = True,
    hide_chrome: bool = True,
) -> str:
    """Compose the full stylesheet injected before capture."""
    parts = [THEME_CSS.get(theme, DARK_THEME_CSS).strip()]
    if hide_metrics:
        parts.append(build_metric_suppression_css().strip())
    if hide_chrome:
        parts.append(
            f"{_selector_list(CHROME_SELECTORS)} {{\n"
            "    display: none !important;\n"
            "}\n"
        )
    parts.append(
        f"{TWEET_CARD_SELECTOR} {{\n"
        "    border-radius: 12px;\n"
        "    border: 1px solid #2f3336;\n"
        "    margin: 0 auto;\n"
        "}\n"
    )
    return "\n".join(part for part in parts if part)


def build_injection_script(
    selectors: tuple[str, ...] = METRIC_SELECTORS,
    *,
    hide_metrics: bool = True,
) -> str:
    """Return the JS executed in-page to strip metrics from the live DOM.

    Inline styles are used in addition to the stylesheet because Twitter's own
    runtime re-renders parts of the card after hydration.
    """
    selector_json = ", ".join(f'"{selector}"' for selector in selectors)
    metrics_block = (
        f"""
    const METRIC_SELECTORS = [{selector_json}];
    for (const selector of METRIC_SELECTORS) {{
        document.querySelectorAll(selector).forEach((node) => {{
            if (node instanceof HTMLElement) {{
                node.style.setProperty('display', 'none', 'important');
                node.setAttribute('aria-hidden', 'true');
            }}
        }});
    }}
"""
        if hide_metrics
        else ""
    )

    return f"""
(() => {{
    document.documentElement.setAttribute('data-sidekick-capture', 'true');
{metrics_block}
    const cards = document.querySelectorAll('{TWEET_CARD_SELECTOR}');
    cards.forEach((card) => {{
        if (card instanceof HTMLElement) {{
            card.style.setProperty('margin', '24px auto', 'important');
            card.style.setProperty('max-width', '700px', 'important');
        }}
    }});
    return cards.length;
}})();
""".strip()


def build_capture_styles(render_config: Any) -> str:
    """Build the stylesheet from a :class:`src.config.RenderConfig` instance."""
    theme_raw = str(getattr(render_config, "theme", "dark"))
    theme: Theme = "light" if theme_raw == "light" else "dark"
    hide_metrics = bool(getattr(render_config, "hide_metrics", True))
    return build_card_css(theme=theme, hide_metrics=hide_metrics)


def build_capture_script(render_config: Any) -> str:
    """Build the DOM script from a :class:`src.config.RenderConfig` instance."""
    hide_metrics = bool(getattr(render_config, "hide_metrics", True))
    return build_injection_script(hide_metrics=hide_metrics)


__all__ = [
    "CHROME_SELECTORS",
    "DARK_THEME_CSS",
    "DEFAULT_VIEWPORT_HEIGHT",
    "DEFAULT_VIEWPORT_WIDTH",
    "LIGHT_THEME_CSS",
    "METRIC_SELECTORS",
    "THEME_CSS",
    "TWEET_CARD_SELECTOR",
    "Theme",
    "build_capture_script",
    "build_capture_styles",
    "build_card_css",
    "build_injection_script",
    "build_metric_suppression_css",
]
