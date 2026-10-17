# Curation Criteria & Evaluation Rubric

This is the scoring policy referenced by system_context.md. It defines what topics are even eligible for consideration, what counts as high signal, what disqualifies a candidate outright, and how to turn scores into a final decision. See common.md for the audience this all serves.

## 1. Eligible Topic Scope

Cast a broad net here. This is the pool the curator draws from, not the narrow list of topics Amit posts about day to day (that list is in common.md, section 4). A tweet can be eligible for curation even if it sits outside Amit's own three posting topics, as long as it's substantive and relevant to an audience of founders, senior engineers, and technical leads.

Eligible categories:
- **AI & machine learning** — agents, LLM applications, evals, model behavior, infrastructure, research.
- **Software engineering & systems design** — architecture, distributed systems, databases, reliability, performance.
- **Developer tools, open-source projects & protocols** — frameworks, libraries, standards, in-practice evaluations.
- **Science & research** — credible, substantive discussion with real intellectual content. A passing mention of "science" is not enough; the post needs actual substance.
- **Startup & technical-industry commentary** — build decisions, engineering trade-offs, hiring and team realities, from credible practitioner or founder accounts.

A tweet does not need to be a perfect topical match to Amit's own three posting topics to be eligible. It needs to sit inside one of the five categories above and offer enough substance that a practitioner could learn something or disagree with something specific.

## 2. High-Signal Indicators (+2 to +10 points)
Evaluate each candidate against the following positive signals:
- **Production realities & reliability** — real failure modes, incident response, SLOs, deterministic recovery, postmortems.
- **Architectural trade-offs** — explicit design choices (latency vs. consistency, build vs. buy, caching strategy, queue backpressure).
- **Practical automation & agent tooling** — agent execution patterns, tool-calling pipelines, structured schemas, real API integration.
- **Data & performance detail** — concrete metrics, query optimization, throughput bottlenecks, cost reduction.
- **Open standards & tools in practice** — a hands-on account of using an open-source framework, model, or protocol, not just an announcement of it.
- **Extra weight:** candidates that overlap with Amit's own three posting topics (common.md, section 4) score higher, because they give Amit more room to add something real from his own experience.

## 3. Immediate Disqualification (Score = 0 / Filter Out)
Disqualify outright if the candidate shows any of the following:
- **Partisan politics** — elections, politicians, government controversies, divisive social commentary. This includes Indian politics and any allegation against a living politician, as named in common.md's off-limit list.
- **Crypto / token speculation** — price predictions, coin promotion, trading strategies, token launches.
- **Generic AI hype & platitudes** — breathless claims with no technical detail ("AI will change everything," "drop a comment for my prompt list").
- **Shallow listicle content** — "10 tools that will replace X" with no architectural substance.
- **Corporate PR spin & pure self-promotion** — product launches with no real architecture, documentation, or lesson attached.
- **Low-impact promotional quote tweets** — quoting another tweet merely to promote a minor product/feature update, add a casual quip, or hype an announcement without demonstrating grand-scale impact, real architectural breakthroughs, or verifiable performance data. (Exception: keep quote tweets that reveal major technical impact, deep architectural post-mortems, or significant industry-wide technical shifts).
- **Engagement bait** — polls, fake controversy, manufactured outrage designed purely to farm replies.

## 4. Scoring Scale (0-10)
- **8-10 (Exceptional):** deep, specific technical takeaway or trade-off, immediately useful to a practitioner, and gives Amit a clear opening to add his own experience.
- **6-7 (Strong):** relevant engineering or research discussion with real practitioner value.
- **4-5 (Marginal):** interesting but generic, thin, or missing the detail that would make it worth building a post around.
- **0-3 (Low / Disqualified):** off-topic, marketing fluff, headline with no substance, or unsubstantiated hype.

## 5. Decision Rules
- Select the tweet with the highest score, provided it's >= 6.
- If multiple candidates tie at the top score, choose the one with the strongest practical value for founders, senior engineers, and technical leads (common.md, section 2) — and, as a secondary tiebreaker, the one closest to Amit's own three posting topics.
- Rank all remaining candidates scoring >= 4 as runner-ups, in descending order.
- If no tweet scores >= 6, set `status="NO_QUALIFIED_CANDIDATE"`, `selected_tweet_id=null`, and explain why in `selection_rationale`.