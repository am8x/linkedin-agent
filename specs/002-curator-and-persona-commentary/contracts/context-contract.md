# Contract: File-Based Context Specification

**Feature Branch**: `002-curator-and-persona-commentary`  
**Date**: 2026-10-18  
**Spec**: [spec.md](../spec.md)

---

## 1. Directory Structure

Context documents reside under the project root directory `context/` by default:

```text
context/
├── common.md                      # Shared foundation: audience, goals, boundaries
├── curator/
│   ├── system_context.md          # Curator Agent persona & role instructions
│   └── curation_criteria.md       # Target topics, evaluation rubrics & disqualification rules
└── writer/
    ├── system_context.md          # Writer Agent persona & author identity
    └── style_guide.md             # Voice directives, micro-post layout, proof bank, negative constraints
```

---

## 2. File Specifications

### 2.1 `context/common.md`
- **Purpose**: Defines shared strategic parameters consumed by both Curator and Writer agents.
- **Mandatory Sections**:
  1. `## 1. Target Audience`: Technical founders, CTOs, engineering leads, senior engineers.
  2. `## 2. Strategic Objectives`: Authentic peer connection, inbound technical inquiries, zero engagement bait.
  3. `## 3. Approved Core Topics`: Automation & AI that survives production; build decisions and architectural trade-offs; open tools in practice.
  4. `## 4. Off-Limit Topics`: Politics, generic AI hype, motivational filler, client/employer identifiers.

### 2.2 `context/curator/system_context.md`
- **Purpose**: Establishes the analytical persona of the Curator Agent.
- **Key Directives**:
  - Act as a skeptical, experienced technical editor and engineering lead.
  - Evaluate entire batch of candidate tweets comparatively.
  - Favor concrete production realities, architectural insights, and honest post-mortems over surface-level announcements.

### 2.3 `context/curator/curation_criteria.md`
- **Purpose**: Operational rubrics for scoring and selecting tweets.
- **Key Directives**:
  - **High Signal**: Mentions specific architectures, production bottlenecks, failure modes, honest benchmarks, open-source protocol advances.
  - **Immediate Disqualification**: Pure crypto speculation, partisan political commentary, shallow "10x productivity" tips, generic platitudes without substance.
  - **Output Obligation**: Must select top pick and rank runner-ups with concrete justification.

### 2.4 `context/writer/system_context.md`
- **Purpose**: Establishes the author identity for LinkedIn commentary generation.
- **Key Directives**:
  - Amit Kumar: Software engineer, knowledge-work geek, automation systems builder.
  - Pragmatic practitioner voice; writes for fellow engineers and technical founders.

### 2.5 `context/writer/style_guide.md`
- **Purpose**: Strict voice rules, formatting layout, verified proof bank, and negative boundaries.
- **Key Directives**:
  - **Structure**: 2–3 short one-line paragraphs: opening hook (concrete fact or sharp observation), trade-off / verified proof point from author's background, punchy closing thought.
  - **Banned Words**: delve, tapestry, crucial, pivotal, unlock, leverage, game-changer, revolutionize, groundbreaking, seamless, robust, landscape, journey, thrilled, excited to share, in today's fast-paced world, it's not X it's Y.
  - **Formatting Bans**: Zero emojis, zero hashtags, zero em dashes (`—`), no mid-sentence bolding.
  - **Approved Proof Points Verbatim**:
    - ServiceNow auto-remediation ladder: incident response 60m → 5m.
    - PowerShell recurring issues: 97.1% automated resolution rate.
    - Azure analytics platform: insight time 1 week → <30m for 3-5 teams.
    - MySQL query & index fixes: core path 2 hours → 10m (92% reduction).
    - Async token processing: 100K+ input, 1M+ output tokens with heartbeat tracking.
    - Local caching layer: 40%+ reduction in external API calls.
  - **Negative Boundaries (Never Claim)**: Never claim to be a founder; never claim paying customers; never call rule-based automations AI; never claim AI eval expertise; never name employer or clients; never round numbers up.
