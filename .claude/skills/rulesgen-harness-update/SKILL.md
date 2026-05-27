---
name: rulesgen-harness-update
description: Use when a coding or testing session reveals that a Rulesgen harness file (rule, skill, agent, or doc) is inaccurate, incomplete, or blocking correct work. Requires human approval before any harness file is changed.
---

# Rulesgen Harness Update Flow

Harness files (`.claude/rules/`, `.claude/skills/`, `.claude/agents/`, `.claude/CLAUDE.local.md`, root `CLAUDE.md`) are the operating instructions for all agents working on this project. They must not be changed autonomously — every update requires explicit human approval.

## Trigger conditions

Propose an update when:
- A rule contradicts the current code (e.g. lists a Flask convention while the code is FastAPI).
- A skill points at a command that no longer works (e.g. references `python -m pytest` while the project uses `uv run pytest`).
- A path/glob in a rule frontmatter does not match the actual directory layout.
- An agent's tool list is too broad or too narrow for its actual responsibility.
- A `CLAUDE.md` "project facts" item is stale (version bump, dependency change, new module).
- A new common failure mode has appeared that no existing skill covers.

## Workflow

1. Identify the specific harness file(s) and the exact lines that are wrong, missing, or misleading.
2. Quote the current text and propose the replacement text side-by-side.
3. Explain the trigger: what session, what failure, what consequence.
4. **Stop and request human approval** — do not edit the harness file in the same turn.
5. After approval, apply the change in a single, minimal commit (`docs:` Conventional Commit type).
6. Cross-check: a change to one file may need a mirrored change in another (e.g. updating `rulesgen-test-selection` may require an update to `testing-contract.md`).

## Do not

- Do not auto-update the harness during a feature implementation session.
- Do not silently add new agents, skills, or rules without approval.
- Do not edit `.claude/settings.json` permissions to "make a command work" — escalate the underlying need instead.
