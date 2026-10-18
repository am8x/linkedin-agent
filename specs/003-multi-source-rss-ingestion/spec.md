# Feature Specification: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary

**Feature Branch**: `003-multi-source-rss-ingestion`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "so i would like you to define aspect of this project so currently the world flow to the best of my understanding is that we first So first it reads the most recent tweets based on the configuration from the specified accounts, then there is this curator layer which selects a tweet on which we want to base our content, and then the commentator or writer adds in the content or commentary on top of that, and then there is a posting that dry run is not published. Now so the first layer in which we ingest all the, in which we ingest all the tweets, is sort of ingestion layer in which we get the data that we want to work on from the sources, so in that layer along with the tweet or Twitter channel that we have I would like to add another channel and this one would be news articles and that and in this similar to the accounts we would read the RSS feed of some websites that would also be specified in the config similar to the accounts and in the curator the curator would basically then along with the tweets also ingest some of the eligible news articles and yeah then the curator would basically have more options to pick from and in case when a news article is In case when the news article is picked we would fetch all the content of the news article along with the associated image and then we would do some sort of commentary on top of that. And yep, that's the whole thing. Currently, we are just adding another channel for the sources, and that's the whole thing."

## Clarifications

### Session 2026-10-18

- Q1: How should the system format and prepare the visual asset when an RSS news article is selected? → A: Option B (Rendered News Card): Generate a unified branded "news card" screenshot (showing publication name, headline, article lead image, and domain) via a headless browser/renderer similar to how tweets are rendered as cards, ensuring visual consistency across all feed types.
- Q2: What depth and scope of article content should be extracted and provided in the prompt to the Writer Agent? → A: Option A (Full Body, No Character Cap): Extract the complete sanitized main-text body (stripping navigation headers, footers, advertisements, and page boilerplate) with no artificial character ceiling, providing the complete article content to the Writer Agent.
- Q3: Where and how should the original article URL and source publication be referenced in the published LinkedIn post? → A: Reach-Optimized Strategy (Options B & C): To maximize organic LinkedIn reach and avoid algorithmic downranking of posts containing outbound URLs, post commentary incorporates natural publication attribution governed by the writer style guide (`context/writer/style_guide.md`) without outbound links in the post body, while the canonical article URL is staged for placement in the first comment.
- Q4: How should the system deliver the first-comment article link when publishing an RSS news article to LinkedIn? → A: Option A (Automated API Post with Fallback): Attempt to post the first comment automatically via LinkedIn's API immediately after creating the main post; if the API call fails or lacks permission, print the formatted link prominently in the terminal and logs for manual pasting.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Source Content Ingestion (Twitter & RSS News Feeds) (Priority: P1)

As a content curator and technical professional, I want the system's ingestion layer to monitor both configured social accounts and designated website RSS news feeds, so that fresh industry articles are discovered alongside relevant social posts in a single unified candidate collection run.

**Why this priority**: Expanding ingestion beyond Twitter to include high-signal industry news feeds ensures a richer, more diverse candidate pool and prevents content drought when social feeds are quiet or off-topic.

**Independent Test**: Can be tested by configuring both Twitter accounts and RSS feeds, running ingestion, and verifying that new items from both channels published within the lookback window are gathered, validated, and deduplicated against already-published items.

**Acceptance Scenarios**:

1. **Given** configured RSS news feeds and Twitter accounts with recent publications within the lookback window, **When** ingestion runs, **Then** eligible items from both Twitter accounts and RSS feeds are gathered into an unposted candidate pool.
2. **Given** an RSS article previously published or recorded in the publication ledger, **When** ingestion runs, **Then** the duplicate article is identified and omitted from the active candidate pool.
3. **Given** one or more configured RSS feeds are temporarily unreachable or return invalid formats, **When** ingestion runs, **Then** the failure is logged with feed-specific diagnostic details, valid feeds and Twitter accounts continue processing without interruption, and surviving candidates advance downstream.

---

### User Story 2 - Unified AI Curation Across Diverse Content Formats (Priority: P1)

As a creator curating for senior engineers and technical decision-makers, I want the Curator Agent to evaluate candidate tweets and candidate news articles within the same evaluation batch against my strategic goals and persona criteria, so that the single highest-value piece of content is chosen regardless of which channel it originated from.

**Why this priority**: Intelligent cross-channel curation ensures that format or source does not bias selection—only relevance, engineering depth, and alignment with target audience determine which topic gets published.

**Independent Test**: Can be tested by presenting a mixed batch containing 3 tweets and 3 news articles to the Curator Agent, verifying that all candidates are evaluated with the same scoring rubric, and confirming that the agent selects exactly one winning candidate with a comparative justification.

**Acceptance Scenarios**:

1. **Given** a mixed pool of candidate tweets and eligible news articles, **When** the Curator Agent evaluates the pool, **Then** it evaluates each candidate against shared strategic audience and topic rubrics, selects exactly one winning candidate (tweet or article), and ranks eligible runner-up items.
2. **Given** the Curator Agent selects an RSS news article, **When** emitting its decision, **Then** it provides an explicit rationale explaining why the news article offers greater strategic value or insight than competing candidate tweets and articles.
3. **Given** a batch where neither tweets nor news articles meet quality or topic thresholds, **When** the Curator Agent evaluates the batch, **Then** it cleanly issues a disqualification decision with supporting evaluation notes, preventing low-quality publication.

---

### User Story 3 - Full Article Content & Visual Media Extraction (Priority: P1)

As a content creator, when a news article is selected by the Curator, I want the system to retrieve the full article body text and its associated lead image, and render a branded news card, so that downstream commentary synthesis has complete context and the post has an engaging visual asset for publication.

**Why this priority**: RSS feeds typically contain only brief excerpts or summaries. High-quality persona commentary requires the actual substance of the article, and professional LinkedIn engagement requires a visually cohesive card asset.

**Independent Test**: Can be tested by supplying a curated article link, verifying that clean article body text is fetched without web navigation boilerplate, and confirming that the primary associated article image is resolved, downloaded, and composited into a rendered news card screenshot.

**Acceptance Scenarios**:

1. **Given** a curated news article selection, **When** the extraction stage executes, **Then** the complete main article body text is extracted and sanitized without character caps, stripping navigation headers, advertisements, and page clutter.
2. **Given** a curated news article with an associated lead image, **When** media extraction and rendering execute, **Then** a branded news card screenshot is generated featuring the headline, publication details, and article image, matching the theme and quality of tweet screenshot cards.
3. **Given** a curated news article where no lead image is discoverable in the article page or feed metadata, **When** rendering executes, **Then** the system renders a clean typography-based news card with headline and publication details rather than failing.

---

### User Story 4 - Persona-Aligned Article Commentary & LinkedIn Publication (Priority: P2)

As a thought leader on LinkedIn, I want the Writer Agent to generate insightful commentary on selected news articles that reflects my authentic perspective, personal voice, and factual boundaries, and staging the post with the news card and first-comment link for review and publication.

**Why this priority**: Delivering commentary on news articles requires framing industry events with the author's pragmatic, engineering-focused lens, establishing credible authority while optimizing post reach on LinkedIn.

**Independent Test**: Can be tested by passing a fully extracted news article to the Writer Agent, verifying that the commentary adheres to the 2–3 short paragraph structure, avoids banned buzzwords, cites the source publication naturally without main-body URLs, pairs with the rendered news card, and stages the article URL for the first comment.

**Acceptance Scenarios**:

1. **Given** an extracted news article and curation rationale, **When** the Writer Agent generates commentary, **Then** it synthesizes a concise, opinionated takeaway grounded in the author's persona, adhering to style rules, avoiding banned buzzwords, and naturally citing the publication without external outbound links in the main post text.
2. **Given** live publication mode is enabled, **When** an article post is created on LinkedIn, **Then** the system automatically posts the canonical article link as the first comment via LinkedIn's API, falling back to console and log output if comment API permissions are unavailable; **When** dry-run mode is enabled, **Then** the post commentary, rendered news card asset, first-comment article link, source metadata, and curation notes are saved locally for inspection without dispatching external publication calls.
3. **Given** interactive review mode is enabled, **When** an article is curated, **Then** the operator is presented with the article title, publication source, curator reasoning, draft commentary, rendered card preview, and staged first-comment link with options to approve, regenerate commentary, select a runner-up, or cancel.

---

### User Story 5 - Configurable RSS Feed Administration (Priority: P3)

As a system operator, I want to manage monitored RSS feeds in the configuration file alongside existing Twitter accounts—including feed URL, human-readable publication name, and category tags—so that adding or updating content sources requires no code modifications.

**Why this priority**: Operational flexibility allows easily expanding or pruning monitored publications as content strategy evolves.

**Independent Test**: Can be tested by adding a new RSS feed entry to the configuration, executing an ingestion run, and confirming that the new publication is queried and ingested according to configuration parameters.

**Acceptance Scenarios**:

1. **Given** a new RSS feed configured with a URL and publication name, **When** the system runs, **Then** it automatically loads the feed configuration and queries the new source during ingestion.
2. **Given** an invalid or malformed feed configuration entry, **When** the configuration loads, **Then** the system reports a descriptive validation error identifying the specific feed entry and missing fields.

---

### Edge Cases

- **Feed Unreachable or Rate-Limited**: If an RSS server is down, times out, or returns HTTP 429/500 errors, the system logs the error for that feed, marks it as temporarily unavailable, and proceeds with all other feeds and Twitter accounts.
- **Paywalled or Javascript-Only Articles**: If an article URL behind an RSS item blocks automated reading or serves an empty paywall page, the system detects insufficient extracted text, attempts alternative extraction methods, or falls back to the RSS description/runner-up candidate.
- **Missing or Corrupted Article Images**: If an article does not contain a lead image or the image link returns a 404 or corrupted file, the rendered news card dynamically adapts to a clean headline-centric typography layout (displaying publication title, favicon/domain, publication date, and headline) without failing or displaying broken image artifacts.
- **Article Depth and Content Boundaries**: When full articles are lengthy, the extraction pipeline extracts the complete sanitized article body without truncation, ensuring the Writer Agent receives full technical context while filtering out peripheral website markup.
- **Source Attribution & URL Placement**: To protect LinkedIn algorithmic reach, external article URLs are not injected into the main post body; rather, the post commentary naturally cites the publication source per writer style guidelines, and the canonical article URL is staged for placement in the first comment.
- **Comment API Failure or Missing Permissions**: If posting the first comment via LinkedIn's API fails (e.g. HTTP 403 due to missing comment scope or network timeout), the system records the main post publication as successful and prominently displays the staged first comment in the review terminal and execution summary so the user can easily copy and paste it manually.
- **Timezone Inconsistencies Across RSS Feeds**: When different RSS feeds use varying timestamp formats (RFC 822, RFC 3339, or missing timestamps), the system normalizes all timestamps to standard UTC for accurate lookback filtering.
- **High Article Volume from Single Feed**: If a news feed publishes a high burst of articles, ingestion caps the maximum ingested articles per feed to prevent one source from crowding out other publications.

## Requirements *(mandatory)*

### Functional Requirements

#### Configuration & Feed Management
- **FR-001**: System MUST support configuring a list of website RSS/Atom feeds alongside Twitter accounts in the application configuration, including feed URL, source label/name, and optional feed-specific parameters.
- **FR-002**: System MUST validate configured feed definitions on startup and emit actionable error notices if required fields (e.g., URL) are invalid or missing.
- **FR-003**: System MUST respect a configurable lookback window for news items, filtering out articles published prior to the configured cutoff threshold.
- **FR-004**: System MUST allow configuring a maximum number of candidate articles fetched per feed per execution cycle to prevent high-frequency feeds from dominating the candidate batch.

#### Multi-Source Ingestion & Deduplication
- **FR-005**: System MUST fetch and parse recent items from all configured and active RSS/Atom news feeds during each ingestion run.
- **FR-006**: System MUST persist and check each candidate article's unique identifier (canonical URL or GUID) against the publication ledger, filtering out previously published or rejected items.
- **FR-007**: System MUST assemble eligible, unposted items from both Twitter accounts and RSS feeds into a unified candidate pool.
- **FR-008**: System MUST isolate failures across individual sources, ensuring an error in one RSS feed or Twitter account does not halt ingestion for other configured sources.

#### Unified AI Content Curation
- **FR-009**: System MUST present candidate items from both Twitter and RSS feeds to the Curator Agent in a single comparative evaluation batch.
- **FR-010**: System MUST provide candidate metadata (including source type, title, author/publication, snippet/text, and publication date) to the Curator Agent to enable fair evaluation across formats.
- **FR-011**: Curator Agent MUST evaluate all candidates against the shared strategic context (target audience, strategic goals) and curator criteria, selecting exactly one winning candidate regardless of source channel.
- **FR-012**: Curator Agent MUST provide an explicit comparative rationale detailing why the chosen candidate was selected over both competing tweets and competing articles.
- **FR-013**: Curator Agent MUST rank qualifying runner-up candidates across both source types for fallback during interactive review.
- **FR-014**: If no candidate in the unified pool meets the minimum topic and quality thresholds, the Curator Agent MUST emit a structured disqualification decision, halting downstream processing cleanly.

#### Article Content Extraction & Media Acquisition
- **FR-015**: When an RSS news article is selected by the Curator, the system MUST retrieve the article's web page and extract the sanitized body content, removing navigation, footer, advertisement, and boiler-plate text.
- **FR-016**: System MUST extract and resolve the primary lead image associated with the selected article (such as Open Graph image or feed media enclosure).
- **FR-017**: System MUST provide the complete sanitized body text of the selected article to the Writer Agent without an artificial character cap, ensuring full context is available for thoughtful commentary synthesis.
- **FR-018**: System MUST render a styled, branded news card image asset for the curated news article (incorporating publication name/domain, publication date, headline, and lead image if available, with a clean typography layout fallback if no image is present) using the visual rendering engine, ensuring uniform visual styling across both tweet and news post types.

#### Commentary Synthesis & Multi-Source Publication
- **FR-019**: Writer Agent MUST synthesize a concise, persona-grounded commentary for the curated news article, incorporating author voice rules, factual boundaries, and zero banned buzzwords.
- **FR-020**: System MUST support a reach-optimized attribution strategy: the Writer Agent naturally attributes the source publication name within the commentary text per the writer style guide without including external URLs in the post body; the system MUST automatically submit the canonical article URL as the first comment via LinkedIn's API upon post creation, and if the comment API call fails or lacks permission, fall back gracefully by displaying the formatted first-comment link prominently in the terminal and execution logs for manual posting.
- **FR-021**: System MUST present the article title, publication name, curator selection rationale, draft commentary, rendered card preview, and staged first-comment link during interactive editorial review.
- **FR-022**: System MUST allow the operator during interactive review to approve publication, regenerate commentary, select the next-ranked runner-up candidate (tweet or article), or cancel execution.
- **FR-023**: System MUST record the source type (`tweet` or `news_article`), source identifier/URL, publication title, curation rationale, commentary text, and media asset reference in the persistent publication ledger upon publication.

### Key Entities

- **RSS Feed Source**: Configured external website news feed with URL, publication title/label, category tags, and polling settings.
- **Candidate Article Item**: Normalized news item discovered during ingestion, containing canonical URL, GUID, headline/title, publication source, published timestamp, summary snippet, and enclosure metadata.
- **Unified Candidate Pool**: The aggregated, deduplicated collection of eligible candidate tweets and candidate news articles gathered during an ingestion cycle.
- **Extracted Article Context**: The full sanitized body content, metadata, publication details, and resolved lead image of a curated news article.
- **Curated Selection**: The winning item (tweet or article) chosen by the Curator Agent, accompanied by comparative rationale and ranked runner-up items.
- **Multi-Source Publication Record**: Persistent record storing source type (`tweet` vs `news_article`), canonical identifier, commentary, media assets, curator rationale, and external LinkedIn publication identifiers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: **Multi-Source Ingestion Reliability**: 100% of validly configured, accessible RSS feeds and Twitter accounts are queried and processed during each ingestion cycle.
- **SC-002**: **Channel-Agnostic Curation**: 100% of curation decisions select the highest-scoring candidate strictly on topic and audience merit, with zero hard-coded bias toward either tweets or news articles.
- **SC-003**: **Extraction Accuracy**: For 95% of selected non-paywalled news articles, the system successfully extracts clean article text and resolves a valid associated image without operator intervention.
- **SC-004**: **Deduplication Integrity**: 0% of previously published articles or tweets are re-curated or presented as new candidates.
- **SC-005**: **Fault Tolerance**: A failure or timeout in any single RSS feed or external source results in 0 pipeline aborts, allowing all surviving candidate sources to proceed normally.
- **SC-006**: **Persona and Style Compliance**: 100% of synthesized news commentaries adhere to the author's style guidelines, verified proof points, and zero-banned-buzzword standards.
- **SC-007**: **Auditable Ledger Storage**: 100% of published posts (tweets and news articles) are recorded in the publication ledger with complete source attribution and curator reasoning.

## Assumptions

- **Feed Standard Compliance**: Monitored news feeds provide standard RSS 2.0 or Atom XML conforming to standard publication date formats.
- **Article Paywalls**: Sites requiring subscription logins or aggressive anti-bot protections are out of scope for primary automated scraping; feeds should be selected from open technical publications, company engineering blogs, and public news sources.
- **Unified Review Workflow**: The interactive review menu and dry-run execution flow established in Feature 002 will seamlessly support both tweet cards and news articles.
- **Single Publication per Run**: Each execution cycle selects and publishes (or dry runs) exactly one piece of content—either a tweet or a news article—from the combined candidate pool.
- **Image Licensing**: Images extracted from public news articles and company engineering blogs under Open Graph or media tags are used for editorial commentary and attribution on LinkedIn.
