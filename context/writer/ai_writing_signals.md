# AI-Associated Writing Characteristics & Detection Signals (Distilled Research)

This document is a distilled synthesis of empirical findings from computational linguistics, stylometry, and AI-detection benchmark studies. It summarizes the primary statistical, syntactic, lexical, and discourse patterns that distinguish autoregressive model outputs from natural human writing.

---

## 1. Primary Statistical & Stylometric Signals (Tier 1 Evidence — Score 5)

These features represent the actual computational backbone used by statistical classifiers and perplexity-based detection systems:

| Signal | AI Pattern | Human Baseline | Discriminatory Mechanism |
|---|---|---|---|
| **Perplexity** | **Low (20–60 typical)** | **High (80–200 typical)** | Autoregressive models consistently select high-probability, statistically expected tokens, producing smooth, predictable phrasing. Humans use idiosyncratic, surprising, and low-probability domain choices. |
| **Burstiness (`SD/mean`)** | **Low (0.2–0.4 ratio)**<br>SD: ~4.1 words | **High (0.6–1.2 ratio)**<br>SD: ~8.2 words | AI sentences cluster heavily in a narrow 15–28 word band (~85% of sentences). Human text varies widely, naturally mixing abrupt statements (3–8 words) with longer compound sentences (25–45+ words). Threshold `<0.5` is flagged suspicious; `>0.8` is comfortably human. |
| **Present Participial Clauses** | **Elevated (2–5× human rate)** | Less frequent | High frequency of `-ing` participial clauses opening or closing sentences (*"Recognizing this shift, teams are..."*, *"..., bridging the gap between X and Y"*). Robust across GPT, Claude, and Gemini. |
| **Nominalization & Compound Noun Stacking vs Prepositional Unfolding** | **Elevated (1.5–2× human rate)**<br>Mean word length: ~5.86 chars | Lower density; finite verbs; prepositions<br>Mean word length: ~5.24–5.29 chars | AI stacks abstract nouns into synthetic compound clusters (*"corporate equity pledges"*, *"memory bandwidth"*, *"fund structures"*, *"architectural breakthrough"*), lowering the function-word ratio to ~0.33–0.45 (vs. human ~0.505) and inflating word length. Humans naturally unfold compound phrases with prepositions (*"equity holdings of companies"*, *"bandwidth of the memory"*, *"structure of funds"*, *"innovation in architectural design"*), driving function words to $\ge 50.0\%$ (e.g. 46/91 words). |
| **Self-Repetition & Chain-Link Phrasing** | **Low (1.4% typical)** | **Higher (3.5%–5.0% typical)** | AI artificially smooths lexical choices to avoid repeating tokens, creating low n-gram reuse. Humans naturally link adjacent sentences with chain-link repetition: ending sentence $N$ with an anchor (*"...the figures become obvious"*), opening sentence $N+1$ with a demonstrative (*"These figures are merely the capital allocations"*), opening sentence $N+2$ with the exact nominal (*"Capital allocations cannot solve..."*), and repeating parallel frames (*"It has never been a matter of X. It has always been about Y."*). |
| **Em Dash (`—` or `--`)** | **Elevated (2–5× human baseline)**<br>(up to 10–12× in some corpora) | ~0.3–1.1 per 1,000 words (STEM) | AI overuses em dashes as mid-sentence explanatory crutches, parenthetical elaborations, and restatements. |

---

## 2. Syntactic & Discourse Anti-Patterns (Tier 2 Evidence — Score 4)

Instruction-tuned models exhibit identifiable syntactic habits and formulaic discourse structures:

### 2.1 Formulaic Framing & Transitions
- **Additive & Consequence Markers:** Overuse of formal logical transitions (*Additionally, Moreover, Furthermore, Therefore, Thus, Consequently*). Humans favor simple connectors (*and, but, so*) or direct juxtapositions.
- **Negative Parallelism:** Distinctive contrast framing (*"It's not X, it's Y"*, *"This isn't about X, it's about Y"*, *"Less about X, more about Y"*) appears at roughly **3× human frequency**.
- **Throat-Clearing Hooks:** Elevated use of metadiscourse frame markers (*"It's worth noting," "At its core," "Let's unpack," "Needless to say," "Here's the thing"*).
- **'That'-Clause Subjects:** Overuse of noun clauses as sentence subjects (*"That the model generalizes well is surprising"*).
- **Progressive Aspect Overuse vs Active Simple Present:** AI overuses continuous/progressive verbs (*"We are discussing"*, *"you are searching"*, *"you are dropping"*), producing a detached clinical narration. Humans write in direct simple present (*"We talk about"*, *"you drop"*, *"you don't look for"*), asserting action with agency.
- **Natural Conversational Contractions vs Stiff Uncontracted Phrasing (Empirical Score 5, `ZW2X` vs `U8QC`):** Uncontracted text (*"You do not learn... The market does not reward... Truth is not simple"*) combined with rigid template repetition triggers 100% AI scores (`ZW2X`). Spoken contractions (*don't*, *doesn't*, *it's*, *can't*, *won't*) are a core signature of authentic human writing (*"Learning happens only when you don't take care of your ego... The market doesn't pay anyone... It's not easy"*), scoring 3% AI / 100% human (`U8QC`).
- **Asymmetric Thought Flow vs Formulaic Symmetry:** LLMs replicate identical syntactic formulas across consecutive paragraphs (e.g., repeating `[Negative statement] + [Instead, ...]` in back-to-back paragraphs). Human prose breaks symmetry, varying its rhetorical movements naturally across paragraphs (*Rather,*, *On the contrary,*, *In reality,*, *The catch is*).
- **Vivid Idiomatic Expressions vs Literal Token Swaps:** Human prose uses rich, idiomatic collocations (*"take care of your ego"*, *"let go of your old assumptions"*, *"confronted with data that is inconsistent"*, *"disappears the minute you stop auditing your moves"*) rather than stiff, literal token swaps (*"protect your ego"*, *"drop your previous assumptions the moment logs contradict"*).
- **Detached Passive vs Direct Practitioner Address:** AI uses generic third-person articles (*"optimizing a loss function"*, *"dropping prior assumptions"*). Humans address the practitioner directly (*"your loss function"*, *"all your old assumptions"*, *"your moves"*), naturally integrating personal pronouns that boost function-word density.
- **Candid Human Vulnerability vs Pretentious Axioms:** AI defaults to sweeping, pseudo-profound axioms (*"Truth is not simple"*); human text frequently delivers candid, grounded admissions (*"It's not easy."*).
- **Everyday Phrasal English vs Synthetic Litotes:** Avoid forcing synthetic litotes formulas (*"is not an easy one"*). Humans use natural phrasal idioms (*"is not simple"*, *"is difficult"*, *"look for"*, *"is no longer there"*).

### 2.2 Epistemic Hedging vs. Boosters
- **The Non-Committal Hedge:** AI text heavily stacks weak modals and probability verbs (*may, might, could, would, potentially, suggest, indicate, appear, seem, tend to*).
- **Suppressed Boosters:** Humans display a much wider range of firm conviction markers (*clearly, definitely, certainly, obviously*). AI suppresses boosters in favor of cautious, spineless neutrality.

### 2.3 Rhetorical Structure & Endings
- **Three-Part Symmetry:** Predictable three-section structures (Premise $\rightarrow$ Elaboration $\rightarrow$ Summary/Conclusion) and balanced *"on the one hand... on the other hand"* framing.
- **Formulaic Closures:** AI reflexively ends texts with a generic summary bow, a moral lesson, or an abstract recommendation (*"It is important to...", "Moving forward, we must..."*). Humans frequently close on a specific technical constraint, unresolved trade-off, blunt punchline (*"The intuition is lost."*), or parallel cadence (*"It has never been a matter of X. It has always been about Y."*).
- **Lexical Smoothing & Self-Repetition:** AI avoids repeating words within close proximity by cycling through a mental thesaurus. This creates an unnaturally low 3-gram repetition score (~1.4%) that classifiers detect; humans naturally repeat key domain anchor terms across sentences.

---

## 3. Lexical Markers & Vocabulary Elevation (Empirical Ratios)

While statistical detectors rely primarily on perplexity and burstiness, corpus studies confirm extreme frequency elevation for specific words in post-2022 LLM text:

### 3.1 High-Elevation Single-Word Markers
- **Academic/Formal Elevators (~10–28× human baseline):** `delve` (~25–28× in post-2022 corpora), `underscore` (~14×), `showcase` (~10–11×).
- **Metaphorical & Complexity Evaluatives (~60–150× human baseline):** `tapestry` (~150× in GPT/Claude corpora), `camaraderie` (~150× in GPT variants), `unease` (60–100× in Llama variants), `palpable`, `intricate`, `meticulous`, `pivotal`, `multifaceted`, `realm`, `landscape`, `testament`, `robust`, `seamless`, `leverage`, `harness`, `unlock`, `elevate`, `foster`, `friction`, `scaffolding`, `bottleneck`, `bottlenecks`.
- **Detector-Flagged High-Frequency AI Signals & Bigrams:** `mental model`, `rewrite the core logic`, `category error`, `fundamental`, `fundamentally`, `simply`, `merely`, `consequently`, `substitute`, `limitations`, `organizations`, `signaling`, `altruistic`, `optics`, `undisturbed`, `distribution curves`, `growth over ego`, `echo chamber`.

### 3.2 Corporate Clichés & Generic Evaluatives
- **Business/Marketing Clichés:** `move the needle`, `game-changer` / `game changer`, `paradigm shift`, `best practices`, `stakeholders`, `ecosystem`, `synergy`, `optimize`, `streamline`, `scalable`.
- **Generic Evaluative Adjectives:** `crucial`, `critical`, `essential`, `comprehensive`, `groundbreaking`, `revolutionize`, `breakthrough`, `breakthroughs`.

---

## 4. Model-Family Fingerprints

Stylometric classifiers can attribute the originating model family with 73–87% accuracy based on persistent stylistic signatures:

| Model Family | Distinctive Empirical Patterns |
|---|---|
| **GPT (3.5 / 4 / 4o / 4.1)** | Most rigidly structured; strongly favors three-section organization; predictable transition phrases (*"It's worth noting," "Additionally"*); elevated *tapestry* and *camaraderie*; em dashes 3.28× human baseline (up to ~10.6/1,000 words unconstrained). |
| **Claude (2 / 3 / 3.5 / Opus)** | More conversational tone; nuanced multi-step hedging with explicit reasoning steps; elevated *tapestry* and em dash density (~9.1/1,000 words). |
| **Gemini (1.5 / Pro / Flash)** | Longer sentences with deeply nested/embedded clauses; consistent paragraph structure; academic-style vocabulary and complex logical connectors. |
| **Llama (2 / 3 / variants)** | Distinctive vocabulary preferences (*unease* 60–100× human rate; *palpable*, *intricate* preferred); less rigidly structured than GPT. |

---

## 5. False-Positive Risk Factors (What Mimics AI)

Classifiers frequently produce false positives (up to 61% on non-native/ESL writing and heavily edited corporate prose) when human text accidentally displays:
1. Low burstiness (uniformly medium-length sentences produced by rigid template writing or heavy copy-editing).
2. Formulaic transition markers (*"Furthermore," "Moreover," "In conclusion"*).
3. Overly dense nominalizations and academic hedging without personal voice.
4. Over-suppression of natural sentence variation and conversational function words.
