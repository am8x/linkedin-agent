# LinkedIn Sidekick - ADK

An autonomous, agentic companion for cross-posting curated tweets to LinkedIn with AI-synthesized commentary, high-DPI rendering, and speculative planning workflows.

## Features

- **Spec-Driven Architecture**: Powered by GitHub Spec Kit (`specify`) with multi-agent integrations for **Antigravity** (`.agents/`) and **OpenCode** (`.opencode/`).
- **Autonomous Agent Workflows**: Interactive specification, planning, and task convergence (`/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`).
- **Idempotent Persistence**: SQLite-backed publication ledger preventing duplicate cross-posts.
- **Robust Grounding**: Real-time context grounding using Google Search and Google Interactions API.
