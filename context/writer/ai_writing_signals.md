# AI-Associated Writing Characteristics — Knowledge Base

## 0. Core Principles

- **No single feature is diagnostic of AI authorship.** Strongest evidence supports multi-feature convergence, not individual "tells."
- Two distinct evidence families exist: (1) **statistical/stylometric detection signals** (perplexity, burstiness, token probability, classifier output) that actually power AI-detection systems, and (2) **surface lexical/stylistic "AI tells"** (specific words, phrases, punctuation) that are popular folklore with weaker, more context-dependent support.
- Lexical and stylistic signals are **population-level/probabilistic**, not proof in individual cases.
- **False-positive risk is severe**, especially for ESL/EFL writers, professional/formal writers, and heavily edited text — this qualification applies throughout and should not be dropped when citing any individual feature.
- Model-specific and genre-specific differences are substantial; a feature's strength varies by model family, genre, and time period.
- Findings below draw on peer-reviewed computational linguistics/stylometry studies, corpus analyses, AI-detection technical documentation, and large-scale corpus studies (approx. Jan 2023–Sep 2026). Limitations of the underlying evidence base: rapid model evolution may date pre-2025 findings; GPT-family models are over-represented relative to Claude/Gemini/Llama/Mistral; English-language bias; raw-AI-output vs. AI-assisted/human-edited text is often conflated in source studies; detection-vendor claims rely on proprietary/self-published data.

**Evidence Score Key:** 5 = strong empirical evidence across multiple high-quality studies; 4 = good empirical evidence with limitations; 3 = moderate/limited replication; 2 = weak/indirect; 1 = mostly anecdotal; 0 = unsupported/contradicted.

---

## 1. Vocabulary & Lexical Patterns

### 1.1 High-evidence single-word markers (elevated frequency in AI text)

| Word | Function | Elevation | Genres | Evidence | Confidence | Caveats |
|---|---|---|---|---|---|---|
| delve(s/d) | investigate deeply | ~25–28× expected rate in post-2022 PubMed abstracts | Academic, formal | 5 | High | Prompt-dependent; declining in 2025–2026 models; co-occurs with *underscore* in ~96.5% of joint cases (2023–2024) |
| underscore(s/d) | emphasize | ~14× expected rate | Academic, formal | 5 | High | Declining utility |
| showcase(s/d/showcasing) | display/demonstrate | ~10–11× expected rate | Academic, marketing | 5 | High | Promotional human contexts also elevate this word |
| tapestry | complex interwoven structure (metaphor) | ~150× in some GPT corpora | Academic, creative | 4 | Medium-High | Genre- and model-dependent (elevated for Claude/GPT specifically) |
| camaraderie | fellowship | ~150× (ChatGPT variants) | Narrative | 4 | Medium | Model-specific (GPT) |
| palpable | tangible/perceptible | Elevated across models | Descriptive | 4 | Medium | GPT and Llama both prefer |
| unease | anxiety | 60–100× (Llama variants) | Narrative | 4 | Medium | Model-specific (Llama) |
| intricate, meticulous, pivotal, multifaceted, realm, landscape, testament, robust, seamless, leverage, harness, unlock, elevate, foster | various (complexity/emphasis/utility evaluatives) | Consistently elevated but discipline- and genre-dependent | Academic, business, marketing | 3–4 | Medium | Many of these are also very common in ordinary human academic/business writing (esp. *realm*, *landscape*, *pivotal*, *multifaceted*, *robust*) → high false-positive risk when used alone |

### 1.2 Corporate/professional cliché vocabulary
move the needle, game-changer, paradigm shift, best practices, stakeholders, ecosystem, synergy, optimize, streamline, scalable — elevated in AI business/marketing text; also common in human corporate writing (medium-high false-positive risk).

### 1.3 Generic evaluative adjectives
important, significant, critical, crucial, essential, valuable, useful, effective, comprehensive, thorough — very frequent in AI text but ubiquitous in ordinary human writing; weak standalone signal (low specificity, high false-positive risk).

### 1.4 Cross-cutting caveats for §1
- Elevation is measured against pre-2022 baselines; degree varies by corpus, model, and genre.
- Single-word blacklists are **not used by actual detection systems** (see §10); they are a folklore layer distinct from statistical detection.
- Temporal trend: usage of flagged words is **declining** as models adapt and human writers deliberately avoid them.

---

## 2. Phrases, Discourse Markers & Collocations

### 2.1 Transitions and framing phrases
| Phrase/pattern | Function | Pattern | Genres | Confidence |
|---|---|---|---|---|
| Additionally, Moreover, Furthermore, Therefore, Thus, Consequently | additive/consequence transitions | Elevated in AI text; *However* is most frequent transition in both AI and human academic writing | Academic, formal | Medium |
| "On the one hand… on the other hand…" | balanced contrast framing | Elevated in AI | Argumentative | Medium |
| "It's worth noting," "at its core," "let's unpack," "needless to say" | framing/hook phrases | Very high frequency, especially GPT-4o/ChatGPT | Explanatory, all models | Medium |
| "In conclusion," "In this paper/essay/study," "This study examines…" | summary/self-reference markers | Elevated in academic AI text | Academic, essays | Medium |
| Negative parallelism: "It's not X, it's Y" | rhetorical contrast | ~3× human frequency | All genres | Medium |

**Caveat:** All of the above are also standard human academic/rhetorical conventions (especially transitions and three-part balanced contrasts); elevated frequency, not exclusivity, is the finding. False-positive risk: medium-high.

### 2.2 Hedging and epistemic markers
| Marker type | Examples | AI vs. human | Notes |
|---|---|---|---|
| Modal verbs | may, might, could, would, should, can | Substantially elevated in AI academic text (e.g., one corpus: "may" AI 119 vs. human 13; "can" AI 341 vs. human 65) | Academic conventions also encourage hedging → false-positive risk high |
| Epistemic verbs | suggest, indicate, appear, seem, tend to | Most frequent hedge verbs in AI text | — |
| Probability adjectives/adverbs | likely, possible, potentially, approximately | Elevated in AI | "possible" common in both AI and human text |
| Boosters (opposite pole) | clearly, definitely, certainly, obviously | Reduced/absent in AI text in at least one corpus study; humans show wider booster range | Varies by prompt and genre |
| Engagement markers | you, we, let's, consider this | Less frequent in AI text | — |

**Interpretation:** AI text shows heavy hedging without commitment — frequent hedges paired with sparse boosters — producing a cautious, non-committal tone. Example contrast — AI: "This may suggest that the results indicate a potential relationship…"; Human: "The results clearly show a relationship…" / "We argue that…"

---

## 3. Syntax & Grammar

| Feature | AI pattern | Human baseline | Ratio/Difference | Evidence | Confidence | Caveats |
|---|---|---|---|---|---|---|
| Present participial clauses ("Brian, leaning on his agility, dances…") | Elevated | Less frequent | 2–5× human rate | 5 | High | Robust across GPT, Claude, Gemini; genre-dependent |
| Nominalization density ("the implementation of the strategy") | Elevated | Less frequent | 1.5–2× human rate | 4 | Medium | Common in human academic writing too |
| 'That' clauses as sentence subjects ("That the model performs well is surprising") | Elevated | Rare in informal writing | — | 4 | Medium | Distinctive LLM preference; genre-dependent |
| Phrasal coordination ("X and Y and Z") | Elevated | Variable | — | 3 | Low-Medium | — |
| Agentless passive voice ("It was observed that…") | **Less** frequent (opposite of popular belief) | More frequent in human academic writing | GPT-4o ~0.5× human rate | 3 | Low | Contradicts the common "AI overuses passive voice" claim; model- and genre-dependent |
| Syntactic dependency depth | Deeper nesting | — | Elevated in AI | 3 | Low-Medium | Complex human writing also shows depth |
| Constituent length | Shorter | Longer | Human > AI | 3 | Low | Small effect, genre-dependent |
| Dependency-distance optimization (cognitive-ease measure) | Less optimized | More optimized | Human > AI | 3 | Low | Requires parsing; not surface-observable |
| Type-token ratio (TTR) | Slightly lower (e.g., 0.671 vs. 0.683) | Slightly higher | — | 4 | Medium | Small effect; length-sensitive |
| Lexical density (content words/total) | Higher (e.g., 0.771 vs. 0.696) | Lower | — | 3 | Low-Medium | Overlaps with human technical writing |
| Lexical sophistication | Higher (e.g., 0.596 vs. 0.436) | Lower | — | 3 | Low | Counterintuitive; not diagnostic alone |
| Average word length | Longer (e.g., 6.95 vs. 5.94 characters) | Shorter | — | 3 | Low | Small effect |
| Hapax legomena (words appearing once) | Fewer | More | — | 3 | Low-Medium | Length-sensitive |
| Numbers/symbols, auxiliaries (modal verbs), pronouns | More frequent in AI | Less frequent | — | 3 | Low-Medium | Overlaps with technical/academic human writing |
| Grammar/spelling errors | Substantially fewer | More (esp. student writing) | — | 4 (confounded by editing) | Medium | Editing confounds this signal; not zero-error, and edited human text can also be error-free |

**Overall interpretation:** Instruction-tuned models favor a noun-heavy, informationally dense style even when explicitly prompted toward informal register; this style is one of the more model-family-robust markers (present participial clauses, nominalization) but individual grammatical features overlap substantially with formal human writing conventions.

---

## 4. Sentence Structure & Burstiness

**Status: one of the strongest and most stable indicators (Evidence Score 5).**

Burstiness = variation in sentence length/structure across a text. Human writing is high-burstiness (mixed short/long sentences); AI text is low-burstiness (uniform lengths).

| Metric | Human baseline | AI baseline | Discriminatory power |
|---|---|---|---|
| Sentence-length standard deviation | ~8.2 words | ~4.1 words | High |
| Burstiness ratio (SD/mean) | ~0.6–1.2 | ~0.2–0.4 | High |
| Suspicious threshold | >0.8 comfortably human | <0.5 flagged suspicious | High |
| Sentence-length clustering | 4–55+ words, no central cluster | ~85% in 15–28 word range (GPT-4o) | High |
| Structured abstracts (3 subheadings) | mean 83.14, SD 17.15 | mean 64.31, SD 8.24 (statistically significant) | High |
| Structured abstracts (4 subheadings) | mean 94.95, SD 38.38 | mean 70.36, SD 31.48 | High |

**Measurement method:** tokenize into sentences → count words/tokens per sentence → compute mean and SD → coefficient of variation (SD/mean) → compare to thresholds (<0.5 suspicious, >0.8 human-like).

**False-positive risks:** professional/heavily edited prose, technical/STEM writing with dense noun phrases, non-native English writers (formal-instruction uniformity), and AI-edited/heavily revised human text can all show artificially low burstiness.

**Confidence:** High for unedited text; Medium for edited/mixed-authorship text.
**Temporal stability:** Stable — fundamental to token-by-token autoregressive generation; unlikely to change without architectural shifts.

---

## 5. Paragraph & Document Organization

| Feature | AI pattern | Human baseline | Evidence | False-positive risk |
|---|---|---|---|---|
| Paragraph length | Predictable, 3–5 sentences | Also common in professional human writing | 3 | High |
| Internal paragraph structure | Formulaic topic sentence + elaboration + summary | Overlaps with standard essay convention | 3 | Medium |
| Section templates | Predictable: Intro → Background → Methods → Results → Discussion → Conclusion; or simple 3-part Intro/Body/Conclusion | Common human essay/report structure | 3 | High |
| Heading style | Title-case, parallel grammatical structure across headings | More variable in human writing (mixed case, less rigid) | 3 | Medium |
| Summary-then-elaboration pattern | "There are three key factors…" followed by list | More varied in human writing | 3 | Medium |

---

## 6. Discourse Patterns (Metadiscourse)

Using Hyland's metadiscourse framework applied to AI vs. human academic writing:

| Category | Subcategory | AI pattern | Human baseline |
|---|---|---|---|
| Interactive markers | Transitions | Most frequent category; elevated | Frequent but less dominant |
| | Frame markers ("This paper is organized as follows…") | More frequent | Less frequent |
| | Endophoric markers (internal cross-references) | Sparse | More frequent |
| | Code glosses (explanations) | Less frequent | More frequent |
| Interactional markers | Hedges | Elevated | Variable, wider range |
| | Boosters | Less frequent/absent in one study | More frequent and varied |
| | Engagement markers (you, we, let's) | Less frequent | More frequent |
| | Self-mentions (I, we, my, our) | Sparse | More frequent |
| | Attitude markers (unfortunately, importantly) | Less frequent | More frequent |

**Interpretation:** AI text relies strongly on formulaic structural markers (frame markers, transitions) but shows limited sophisticated argumentation (sparse code glosses, endophoric references) and an impersonal register (reduced self-mention, attitude markers).

---

## 7. Rhetorical & Semantic Patterns

| Pattern | AI tendency | Human baseline | Evidence | False-positive risk |
|---|---|---|---|---|
| Three-part organizational structures | Common | Also a standard human organizational pattern | 3 | High |
| Balanced "on the one hand/on the other hand" contrasts | Elevated | Common human argumentative device | 3 | Medium |
| Excessive neutrality/even-handedness, avoidance of strong stance | Documented | More varied stance in humans | 3 | High (prompt-dependent) |
| Semantic redundancy / over-explanation (repeating concepts in different words) | Documented, reduces clarity | More concise typically | 3 | Medium |
| Generic, formulaic conclusions/recommendations ("It is important to…," "should," "consider") | Elevated | More varied | 3 | Medium |

---

## 8. Tone & Voice

| Feature | AI pattern | Human baseline | Evidence | Notes |
|---|---|---|---|---|
| Emotional positivity / motivational language ("exciting," "promising," "important") | More positive | More varied | 4 | LIWC-based analysis |
| Negative emotions (anger, sadness, fear) | Weaker/reduced | Stronger, more varied | 4 | Genre- and prompt-dependent |
| Self-mention / personal voice | Reduced | More frequent | 3 | Overlaps with formal human register |

---

## 9. Punctuation

### 9.1 Em dash (—) — strongest punctuation indicator (Evidence Score 5)

Em dashes appear consistently more often in AI text than in human baselines, though exact multiples vary widely by study, model, and genre (observed ratios ranging roughly 1.7×–12× across different studies/models; commonly cited range 2–5×). Selected data points:
- GPT-4.1: 3.28× human baseline; resistant to prompt-based suppression attempts.
- General prose comparisons: ~2× human rate (also noting a 63% increase in Oxford-comma usage in the same analyses).
- Published-paper comparison: AI ~3.8/1,000 words vs. human STEM ~0.3/1,000, human humanities ~1.1/1,000 (3.5–12× range).
- Large multi-model corpus (700,000+ words): GPT-4.1 ~10.62/1,000 words, Claude Opus ~9.09/1,000 words, vs. estimated human ~5–6/1,000 (~1.7–2× range).
- Chat-log analysis: 37% of ~89,000 AI chats contained an em dash, peaking at 73% in one month (temporal increase noted).
- Training-data corpus comparison: em dashes markedly more frequent in web-text training corpora than reference human-text corpora (offered as a training-data-composition explanation for the pattern).
- Temporal/before-after studies: medRxiv discussion sections rose from 4.23% (pre-Nov 2022) to 11.58% (post) containing em dashes; ecology abstracts' em-dash relative frequency more than doubled 2021–2025 — these are temporal correlations with AI-tool adoption, not proof of causation for any individual document.

**Typical usage pattern:** mid-sentence explanatory asides/parenthetical elaborations, often introducing clarifications, examples, or restatements; frequently co-occurs with words like *delve*, *underscore*, *showcase*.

**False-positive risks:** humanities/journalism/creative-nonfiction writers naturally use em dashes at elevated rates; style guides (e.g., Chicago Manual of Style) encourage em-dash use; individual human writers vary widely in natural em-dash density.

**Temporal stability:** Declining — human writers are actively avoiding em dashes to evade detection, and models may be adapting.

### 9.2 Semicolon (;) — weak/moderate indicator (Evidence Score 3)
Semicolon frequency is reportedly elevated in AI prose and near-zero in informal/professional human writing per some analyses, and semicolons are noted among punctuation marks humans have begun avoiding post-2022 for fear of detection. Web-text baseline ~0.8 occurrences/1,000 tokens. **False-positive risks:** routine in human academic/humanities/social-science writing; may be overused by non-native writers taught formal grammar rules. Confidence: low-medium; not reliable standalone.

### 9.3 Other punctuation features

| Punctuation | AI pattern | Human baseline | False-positive risk |
|---|---|---|---|
| Oxford comma | ~63% increase reported | Common in formal human writing (style-guide driven) | High |
| Colon (elaboration marker) | Elevated in structured output | Common in technical/instructional human writing | High |
| Parentheses (explanatory asides) | Elevated in technical AI text | Common in academic human writing | High |
| Quotation marks | More numbers/symbols/auxiliaries co-occur | Variable | Medium |
| Ellipses | Anecdotally less common in AI | Common in informal human writing | Medium |
| Exclamation marks | Less frequent (AI more emotionally neutral) | Variable by genre | Medium |
| Question marks (rhetorical) | Used in AI explanations | Common in human explanatory text | High |
| Hyphen/dash (general) | ~8–12/1,000 tokens web baseline (conflates hyphen and em-dash counts) | Similar | Low |
| Slash (/) | More symbols generally in AI text | Variable | Medium |
| Bullet characters | Elevated in AI output | Common in human lists | Medium |

### 9.4 Approximate frequency summary (per 1,000 words/tokens)

| Punctuation | Web baseline | AI (estimated) | Human (estimated) | Discriminatory power |
|---|---|---|---|---|
| Period | ~65 | Similar | Similar | Low |
| Comma | ~42 | Similar | Similar | Low |
| Em/en dash | ~8–12 (web); 18–25 in explanatory text | ~18–38 (model-dependent) | ~5–12 (genre-dependent) | Medium-High |
| Semicolon | ~0.8 | ~1.5–3 (estimated) | ~0.5–2 (genre-dependent) | Low-Medium |

---

## 10. Formatting & Markdown (Evidence Score 3–4)

LLMs trained on markdown-heavy data (READMEs, technical docs, structured web content) exhibit elevated use of headings, bullets, numbered lists, and bold/italic emphasis, plus rhetorical patterns like summary-then-elaboration.

| Feature | AI pattern | Human baseline | Discriminatory power |
|---|---|---|---|
| Bullet lists | Frequent, 3–7 items | Variable by genre | Medium |
| Numbered lists | Frequent, sequential steps | Variable | Medium |
| Nested lists | Common in explanatory text | Less common in informal human writing | Low-Medium |
| Bold emphasis | Key terms highlighted | Common in human technical/instructional writing | Low |
| Italic emphasis | Terminology/emphasis | Common in human academic writing | Low |
| Heading hierarchy | Highly regular (H1→H2→H3) | More variable/less regular | Low-Medium |
| "Key Takeaways" sections | Formulaic | Less common in human academic writing | Medium |
| "Conclusion" sections | Explicit labeled | Common in human academic writing too | Low |
| Horizontal rules | Section dividers | Less common in human writing | Low-Medium |
| Code blocks, block quotes, tables | Used in AI technical output | Also common in human technical writing | Low |

**False-positive risks:** human-written technical documentation, business reports/slide decks, and standard academic writing conventions (headings, conclusions, structured organization) naturally exhibit the same markdown-heavy formatting. Confidence: medium for AI-assisted technical/instructional writing; low for general prose.

---

## 11. Statistical & Stylometric Detection Features

These are the actual backbone of detection systems (distinct from the surface lexical/formatting "tells" above).

| Feature | What it measures | AI signal | Human signal | Notes |
|---|---|---|---|---|
| Perplexity | Average token predictability vs. a reference model | Low (20–60 typical) — smooth, expected phrasing | High (80–200 typical) — surprising/quirky phrasing | Core detection signal used by all major detectors; fundamental to autoregressive generation, so temporally stable |
| Burstiness | Sentence-length variation | Low (uniform; ratio <0.5) | High (mixed lengths; ratio >0.8) | Second core signal (see §4 for full data); stable |
| Token-probability signatures | Likelihood of each next token | Consistently high-probability token choices | More unexpected token choices | Foundation of perplexity and of watermarking approaches |
| Stylometric fingerprints | Function-word frequencies, POS patterns, n-gram distributions | Model-specific patterns | Author-specific patterns | Used in classifier-based detection |
| Watermarking | Statistical signals embedded during generation | Detectable via statistical tests | No watermark | Emerging/research-stage; not yet widely deployed as of 2026; some robustness to human editing demonstrated in recent work |
| Embedding-based approaches | Semantic similarity / probability-curvature features | Distinct embedding distributions | Human-like distributions | Research-stage |
| Classifier-based detection | Supervised ML on labeled corpora | Probability output (0–100% AI) | Lower probability | Basis of GPTZero, Turnitin, etc.; independent studies show ~78–84% overall accuracy (not the near-100% often claimed) |
| Type-token ratio, lexical density/sophistication | Vocabulary diversity/richness | Slightly lower TTR, higher density/sophistication in some studies | Slightly higher TTR, lower density | Small effect sizes; length-sensitive |
| Lexical repetition across long outputs | Decreasing diversity with length | AI shows declining lexical diversity over longer generations | Less pronounced decline | Detectable via n-gram analysis |
| Stylometric model attribution | Classifying which model family produced text | 73–87% accuracy across ~7 classes (human + ~6 model families) vs. 14–17% chance | — | Meaningful model-family fingerprinting is possible even though individual-text authorship attribution is harder |

---

## 12. Genre-Specific Patterns (Evidence Score 5 for genre-dependence overall)

| Genre | AI detectability | Key differences |
|---|---|---|
| Academic essays/articles | High | AI more formal, structured, hedged, noun-heavy; human more varied, personal, emotionally nuanced. Largest AI-human gap of all genres because formal/structured writing aligns with AI training. |
| Business writing | Medium-High | AI shows corporate clichés, bullet lists, recommendations; human shows more varied tone/personal voice |
| Journalism | Medium | AI more neutral/structured; human more emotional, varied sentence lengths |
| Marketing copy | Medium | AI shows elevated evaluative language; human more creative/varied |
| Technical documentation | Low-Medium | Both AI and human use structured formatting/lists/bold; AI more rigidly regular |
| Social media | Medium-High | AI more formal, positive, structured; human more informal/emotional/varied |
| Creative writing | Medium | AI more positive, less emotionally intense, more structured; human shows more negative emotion, more variation |
| Casual conversation | Medium | AI struggles to match informal conventions, remains noun-heavy/informationally dense even when prompted otherwise |
| Product descriptions, reviews, reports, emails | Medium | AI shows more promotional/neutral/formal/structured language; human shows more variation, emotion, personalization |

**Cross-genre findings:** instruction-tuned models fail to fully match genre conventions even when explicitly prompted to. Model-vs-model detectability gap also varies by genre: smallest for academic essays (~3–5 point spread between model families in one study), largest for creative writing (~9–14 point spread).

---

## 13. Model-Specific Patterns (Evidence Score 4–5 for model fingerprinting)

| Model family | Distinctive patterns |
|---|---|
| **GPT (3.5/4/4o/4.1)** | Most consistently structured; favors three-section organization; specific transition phrases at identifiable frequencies ("It's worth noting," "Additionally"); narrower vocabulary distribution than humans (*camaraderie*, *tapestry* ~150× human rate); measurable sentence-opening preferences; em dashes 3.28× human baseline (GPT-4.1), up to ~10.62/1,000 words unconstrained; among the most accurately detected by some tools |
| **Claude (2/3/3.5/Opus)** | More variable output, especially tone and sentence structure; nuanced hedging language with explicit reasoning steps; semi-conversational tone, simpler language, step-by-step organization; elevated *tapestry* usage; em dashes ~9.09/1,000 words (Opus 4.6); one study found GPTZero detects Claude at ~95% vs. Turnitin ~88% |
| **Gemini (1.5/Pro)** | Slightly longer sentences with more embedded clauses; strong organization/consistent paragraph structure similar to GPT-4o; academic-style vocabulary, complex sentences, logical connectors; some studies find lower AI-detection scores (more human-like) |
| **Llama (2/3/etc.)** | Distinctive vocabulary (*unease* 60–100× human rate; *palpable*, *intricate* preferred); more variable/less structured than GPT; ~3–5 point detectability spread from GPT-4o in academic essays |
| **Other (Mistral, DeepSeek, Grok, Qwen)** | Stylometric classifiers can attribute model family (human + ~6 model families) at 73.7–87% accuracy, confirming each family has a measurably distinct style |

**Interpretation:** Model attribution via stylometry is possible well above chance. GPT is the most-studied and most consistently structured; Claude is more variable/conversational with nuanced hedging; Gemini leans academic/complex; Llama has distinct vocabulary preferences.

---

## 14. Human False Positives (Evidence Score 5 — critical, severe implications)

### 14.1 ESL/EFL writers
| Finding | Rate | Sample |
|---|---|---|
| Multi-detector average FPR | 61.3% across 7 commercial detectors; 91% flagged by at least one detector | 91 TOEFL essays, non-native speakers |
| Other analyses | "Over 60%" / "up to 61%" | ESL student writing |
| Lower-end estimate | 14–25% | ESL writing (different tool set) |
| Turnitin vs. GPTZero | Turnitin ~6–9% ESL FPR; GPTZero ~1% (vendor claim) | ESL student essays |

**Causes:** low perplexity (consistent/limited vocabulary), low burstiness (uniform sentence lengths from formal instruction), formulaic transitions taught in ESL curricula ("Furthermore," "Moreover," "In conclusion"), dense noun phrases (technical/academic register), over-hedging (uncertainty, L1 transfer).

### 14.2 Professional/technical writers and other high-risk groups
| Group | Risk | Cause |
|---|---|---|
| Professional editors | Medium-High | Polished, uniform prose → low burstiness |
| Technical writers | Medium | Formulaic structure, bullet lists, passive voice |
| Academic writers | Medium | Hedging, transitions, formal register |
| Corporate communications | Medium | Formulaic language, bullet lists, recommendations |
| Writers using grammar-assistant tools | Medium | Editing removes natural variation |
| Students using templates | Medium-High | Formulaic structure/transitions |
| Writers with repetitive personal styles | Medium | Low lexical diversity, uniform sentence patterns |
| Accessibility-focused writing | Medium | Simplified, structured language |
| Heavily edited text generally | Medium | Editing removes natural stylistic variation |
| Speech-like/conversational content | Medium-High | Misclassified as AI due to simplicity |

**Overall false-positive rate ranges:** native English writers ~5–20% (tool/threshold dependent); ESL/EFL writers ~14–61% (tool/sample dependent); academic abstract-style writing tends toward lower FPRs.

**Implications:** no detector score should be treated as sole proof of AI authorship; ESL students are disproportionately affected (equity concern); professional, edited, and formulaic human writing is at elevated risk of false flags.

---

## 15. Detection Methodologies

### 15.1 How detectors actually work (see §11 for the underlying features)
Core pipeline combines perplexity + burstiness as primary signals, layered with stylometric/classifier-based approaches; watermarking and embedding-based methods are emerging but not yet widely deployed.

### 15.2 Major detection tools (comparative)

| Tool | Method | Accuracy (unedited AI) | FPR (native) | FPR (ESL) | Strengths | Limitations |
|---|---|---|---|---|---|---|
| Turnitin | Proprietary transformer classifier + perplexity/burstiness; trained on licensed academic corpora | High (100% in one 2025 study) | ~1–4% | 6–9% (vendor); higher independently | Institutional integration; plagiarism + AI detection | Drops on mixed-authorship text; proprietary; ESL bias |
| GPTZero | Multi-model ensemble: perplexity, burstiness, fine-tuned classifiers | High for unedited; lower after heavy editing | ~1–2% (vendor); 6–8% independent | ~1% (vendor); higher independently | Sentence-level analysis; strong on Claude detection (~95%) | Performance drops on edited text |
| ZeroGPT | Perplexity + burstiness + classifier | Relatively high on original files | Not well documented | Not well documented | Public access | Degraded by paraphrasing tools |
| Writer AI | Classifier-based | Lower than Turnitin/GPTZero | Not well documented | Not well documented | Enterprise focus | Less accurate overall |
| Copyleaks, Originality.ai | Proprietary word/sentence-pattern analysis | High (vendor claims) | Not well documented | Not well documented | Plagiarism/content-marketing focus | Proprietary, unverified |

### 15.3 Folklore vs. actual detector methodology

| Popular claim | Reality | Gap |
|---|---|---|
| "Detectors look for words like *delve* and *underscore*" | Detectors use perplexity, burstiness, token probabilities, classifiers — not word blacklists | Large |
| "Em dashes prove AI authorship" | Em dashes correlate with AI text but are not themselves a detector input feature | Medium |
| "AI detectors are 99% accurate" | Independent studies show ~78–84% overall accuracy; 61% FPR for ESL writers | Large |
| "Detectors give certain, binary verdicts" | Detectors output probabilities; scores are never sole proof of AI authorship | Large |
| "Watermarking is already deployed everywhere" | Research-stage; limited real-world deployment as of 2026 | Medium |

---

## 16. Temporal Stability

| Category | Features | Reason |
|---|---|---|
| **Declining** (aging poorly) | Em dash frequency; specific vocabulary (*delve*, *underscore*, *showcase*); semicolon frequency; Oxford comma frequency; specific transition phrases; three-part structures; "In conclusion"/"Key Takeaways" sections | Humans actively avoiding flagged features; models adapting; prompt engineering can suppress; these overlap with human conventions and are not architecturally fundamental |
| **Stable** (likely to persist) | Perplexity; burstiness/sentence-length variance; token-probability signatures; present participial clauses; noun-heavy informationally-dense style; stylometric model fingerprints; declining lexical diversity in long outputs | Fundamental to autoregressive token-by-token generation and to consistent model-family training data/architecture; hard to change without architectural shifts |
| **Emerging** (increasing usefulness) | Watermarking; stylometric model attribution; embedding-based detection; cross-model ensemble detection | Active research areas improving in robustness (2024–2026) |

---

## 17. Evidence Strength — Tiered Index

*(Full detail for each feature is in the topic sections above; this is a compact cross-reference by confidence tier.)*

**Tier 1 — Strongest (Score 5):** low perplexity; low burstiness/sentence-length variance; token-probability signatures; present participial clauses (2–5× human rate); em-dash frequency elevation (2–5× typical, model/genre-dependent); elevated *delve/underscore/showcase* (10–28× in academic corpora); noun-heavy informationally-dense style.

**Tier 2 — Good supporting evidence (Score 4):** nominalization density; 'that'-clause-as-subject; elevated hedging modals/verbs; high transition-marker frequency; frame markers; slightly lower TTR; emotional positivity/reduced negative emotion; bullet/numbered-list frequency; model-specific vocabulary (*tapestry*, *camaraderie*, *unease*); negative parallelism; reduced boosters; semantic redundancy/over-explanation; reduced self-mention; stylometric model attribution (73–87% accuracy).

**Tier 3 — Weak/contextual (Score 3):** semicolon frequency; Oxford comma frequency; three-part structures; balanced "on the one hand/other hand"; predictable paragraph length; topic-elaboration-summary structure; excessive neutrality; colon usage; bold/italic emphasis; "Key Takeaways"/"Conclusion" sections; regular markdown structure; lexical repetition in long outputs; reduced personal voice; agentless passive voice (counterintuitively *less* frequent in AI, GPT-4o ~0.5× human); longer average word length; higher lexical density/sophistication; more numbers/symbols/auxiliaries/pronouns; fewer grammar/spelling errors; deeper syntactic dependency; shorter constituents; less-optimized dependency distance; fewer hapax legomena.

**Tier 4 — Folklore/unsupported (Score 0–2):**
| Claim | Status | Reality |
|---|---|---|
| Single-word blacklists prove AI authorship | Unsupported | No single word is diagnostic; all signals are probabilistic |
| Em-dash avoidance proves human authorship | Weak | Humans naturally use em dashes; avoidance is a strategic (detection-evasion) behavior, not a natural baseline |
| AI always uses passive voice | Contradicted | GPT-4o uses agentless passive at ~0.5× human rate |
| AI text is always grammatically perfect | Overstated | Fewer errors, not zero; humans can also be error-free |
| AI text is always emotionally flat | Overstated | AI shows emotional positivity, not flatness; varies by prompt |
| All AI text says "In today's fast-paced world" | Exaggerated | Common cliché, not universal; humans also use it |
| AI detectors are >95% accurate in real-world use | Misleading | Independent studies show 78–84% overall accuracy; 61% FPR for ESL writers |
| Turnitin/GPTZero never false-flag humans | False | 5–20% FPR for native speakers; 14–61% for ESL |
| AI text can be reliably identified by "vibe" alone | Unreliable | Human detection accuracy is modest; statistical methods outperform human judgment |
| Watermarking is widely deployed and detectable today | Emerging, not established | Active research; limited real-world deployment as of 2026 |

---

## 18. Research Gaps

**Understudied areas (priority):**
- AI-assisted/human-edited vs. raw AI output (most studies compare raw AI vs. human only) — High
- Long-form text (books, theses, reports) vs. the short-sample focus of most studies — High
- Non-English languages (overwhelming English-language research bias) — High
- Longitudinal tracking of how patterns shift as models/training data evolve — High
- Watermarking robustness to human editing — High
- Ethical/equity implications of detection (ESL bias, false positives, impact on students/professionals) — High
- Multimodal AI output (text+image+code) — Medium
- Dialogue/conversational AI patterns (vs. monologic-text focus) — Medium
- Domain-specific registers (legal, medical, scientific) — Medium
- Impact of prompting style on linguistic fingerprints — Medium
- Cross-genre transfer effects (AI writing in one genre influencing human writing elsewhere) — Low-Medium
- Human perception vs. statistical detection (what surface features people actually notice) — Medium

**Methodological needs:** standardized benchmarks/metrics (studies currently use incomparable corpora); open datasets for replication; clearer operational distinction between AI-generated, AI-assisted, and human-edited text categories; quantitative operationalization of qualitatively-described features; controlled prompting experiments; factorial designs crossing model×genre×language; longitudinal corpora.

---

## 19. Measurement Framework Summary

- **Perplexity:** compute average token-level predictability against a reference language model; AI text typically 20–60, human text typically 80–200 (ranges are approximate and model/genre-dependent).
- **Burstiness:** tokenize into sentences → compute per-sentence word/token counts → calculate mean and SD → burstiness ratio = SD/mean; ratio <0.5 flagged suspicious, >0.8 comfortably human-like.
- **Stylometric/classifier detection:** supervised ML trained on labeled human/AI corpora using function-word frequencies, POS patterns, n-gram distributions; outputs a probability, not a binary verdict.
- **Watermarking:** statistical signal embedded in generation (e.g., biased token sampling), detected via z-test or sum-based statistics; robustness to human editing is an active research question.
- **Model attribution:** stylometric classifiers trained across human + multiple model-family classes achieve 73–87% accuracy (vs. ~14–17% chance for ~7 classes).

**General measurement caveat:** all numeric baselines/ratios above are drawn from specific studies with specific corpora and should be read as illustrative ranges, not universal constants — they vary by model version, genre, prompting, sample length, and editing status.
