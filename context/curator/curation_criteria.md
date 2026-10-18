# Curation Criteria & Evaluation Rubric

This rubric governs how the Curator Agent scores and filters incoming candidates. It is designed to surface high-density signals across the entire landscape of **Technology, Artificial Intelligence, and Science** that enable frontier-level structural reframing.

## 1. Eligible Topic Scope (Broad Tech, AI & Science)
Any candidate sitting inside the broad triad of **Technology, AI, and Science** is fully eligible—with particular emphasis on **every layer of Technology**:

- **Every Piece of Technology (Hardware, Silicon, Systems & Infrastructure):**
  - Semiconductor design, fab lithography, memory/storage economics, custom AI silicon, and hardware supply chains.
  - Data-center power generation, grid interconnects, gas turbines, cooling thermodynamics, orbital compute, and energy infrastructure.
  - Core software engineering, distributed systems, databases, operating systems, compilers, networking bitstreams, cybersecurity, cryptography, and open protocols.
  - Consumer and industrial hardware: 4-tier wearables (audio, HUD, AR, VR), gaming consoles, autonomous vehicles, humanoid robotics, and electromechanical actuators.
- **Artificial Intelligence & Machine Learning:**
  - Frontier model research, pre-training scaling limits, sample-efficient continual learning, biological vs. artificial neural architectures, and value functions.
  - Post-training RL environments, in-distribution vs. out-of-distribution generalization, multimodal perception, and `200ms` real-time interaction loops.
  - Agentic software engineering, computer-use harnesses, active memory compaction, social discretion, and 3-level agent security (Secure/Confidential VMs, Sentinel oversight).
  - AI ecosystem economics: open-weight models vs. closed frontier APIs ("owning vs. renting Software 2.0"), local/edge inference, and token consumption scaling.
- **Fundamental & Applied Science:**
  - Physics, thermodynamics, cryogenic material science, room-temperature superconductors, nuclear fusion/fission, and planetary/orbital energy scaling.
  - Biotechnology, genomics, neuroscience, clinical neuropsychology, brain-computer interfaces, disease therapeutics, and AI-driven mathematical/scientific discovery (e.g., Navier-Stokes).
- **Technical Product Craft, Org Architecture & Platform Strategy:**
  - Essentialist product design ("disappearing utility"), model-product collapse ("the model is the product"), flat AI-native organizational structures ("Company as a Mini-AGI", "Diamond Mining vs. Skyscrapers"), prototype-first engineering, and asymmetric CapEx backstopping.

*Note:* Eligibility does NOT require any overlap with Amit's personal day-job tools or proof bank. Any substantive topic in Tech, AI, or Science qualifies on its own merits.

## 2. High-Signal Indicators (+2 to +10 Points)
Score candidates upward based on the presence and density of these five structural signals:

1. **First-Principles & Sub-Component Bottlenecks (+3 to +5 pts):**
   - Drills beneath surface symptoms to expose the real physical, thermodynamic, or architectural limiting factor two layers down (e.g., casting capacity for turbine blades/vanes, 40% summer cooling + 25% generator reserve multipliers, 2.75x console memory cost inflation, or 1.5 GB/s to 2 KB/s bitstream compression).
2. **Empirical Anomalies & Generalization Truths (+3 to +5 pts):**
   - Exposes a paradox between benchmark scores and real-world behavior (e.g., acing competitive coding evals while looping between Bug A and Bug B), contrasts brute-force memorization with sample-efficient continual learning, or reveals a novel scientific/algorithmic mechanism.
3. **Stack Shifts & Model-Product Collapse (+2 to +4 pts):**
   - Demonstrates how traditional software/UI specs are collapsing into model post-training, how enterprises migrate from rented frontier APIs to owned open weights, or how `200ms` continuous loops replace turn-based interfaces.
4. **Contrarian Exponential Telemetry (+2 to +4 pts):**
   - Provides hard longitudinal numbers or historical step-ladders (T-3 → Today) showing a steep exponential curve that linear conventional wisdom is mispricing.
5. **Essentialist Design & Organizational Legibility (+2 to +3 pts):**
   - Shows how removing mechanical friction, middle-management relays, static roadmaps, or front-stage AI bloat ("Copilot on consoles") produces superior utility and decision velocity.

## 3. Immediate Disqualification (Score = 0 / Filter Out)
Assign an automatic `0` and reject the candidate if it exhibits any of the following:
- **Partisan Politics & Culture-War Bait:** Elections, politicians, domestic/Indian political controversies, or ideological flame wars.
- **Crypto / Token Speculation:** Price targets, meme coins, yield farming, or token launches.
- **Breathless Hype or Doom Platitudes:** Unsubstantiated claims ("AGI is here and jobs are over," "100% P(doom)") with zero mechanism, math, or engineering substance.
- **Shallow Tool Listicles & Prompt Porn:** "10 AI tools that will 10x your workflow" or "Copy-paste this mega-prompt".
- **Empty Corporate PR & Low-Effort Quote Tweets:** Self-congratulatory launch announcements, minor version bumps, or quote tweets that merely add a one-line quip ("Huge if true," "We're cooking") without disclosing architectural trade-offs, hard telemetry, or a genuine paradigm shift.
- **Engagement Bait:** Polls, "Agree?," or "Drop a comment below".

## 4. Scoring Scale (0–10)
- **8–10 (Exceptional / Frontier Signal):** Contains hard mechanism detail, counter-consensus data, or a sharp architectural/scientific tension that immediately unlocks a first-principles structural reframe.
- **6–7 (Strong / Substantive):** Credible engineering, scientific, or product-strategy insight with enough specificity to anchor a rigorous analytical post.
- **4–5 (Marginal / Consensus):** Topically relevant to Tech/AI/Science, but states conventional wisdom ("Business School Professor" level) or lacks the underlying numbers/mechanism needed for a sharp reframe.
- **0–3 (Low / Disqualified):** Hype, PR fluff, shallow listicle, or hits an immediate disqualifier.

## 5. Decision & Tie-Breaking Rules
1. Select the candidate with the highest score, provided `score >= 6`.
2. **Tie-Breaker Hierarchy (when two or more candidates share the top score):**
   - *First Tie-Breaker:* **Structural Reframe Depth**—pick the candidate that exposes a more fundamental governing variable (physics, unit economics, algorithmic generalization, or stack architecture) over incremental product news.
   - *Second Tie-Breaker:* **Specificity of Telemetry**—pick the candidate with verifiable numbers, concrete failure modes, or explicit trade-offs over abstract assertions.
3. Rank all remaining candidates scoring `>= 4` as runner-ups in descending order.
4. If no candidate in the batch scores `>= 6`, set `status="NO_QUALIFIED_CANDIDATE"`, `selected_candidate_id=null` (or `selected_tweet_id=null`), and document why the batch failed the threshold in `selection_rationale`.