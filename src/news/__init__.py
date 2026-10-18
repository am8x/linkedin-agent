"""News ingestion and article extraction domain package.

Exports models, feed fetchers, and article body extractors.
"""

__all__ = [
    "ArticleExtractor",
    "CandidateItem",
    "CandidateSourceType",
    "CardAsset",
    "ExtractedArticle",
    "FeedConfig",
    "FeedFetcher",
    "FirstCommentPayload",
]


def __getattr__(name: str):  # noqa: ANN202
    """Lazy-load module components to prevent circular imports."""
    if name in {
        "CandidateItem",
        "CandidateSourceType",
        "CardAsset",
        "ExtractedArticle",
        "FeedConfig",
        "FirstCommentPayload",
    }:
        from src.news import models

        return getattr(models, name)
    if name == "FeedFetcher":
        from src.news import fetcher

        return getattr(fetcher, name)
    if name == "ArticleExtractor":
        from src.news import extractor

        return getattr(extractor, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
