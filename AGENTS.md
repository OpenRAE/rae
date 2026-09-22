# RAES SDL Agent Rules

Use the repo policy tooling before and after implementation work.

Run only targeted tests locally. Full test, integration, fuzz and completion
suites run in CI/CD only, including after synchronization or reviewer fixes.
Use explicit relevant pytest modules/cases or `verify-fast-feedback`; missing
change classification is never permission to run the full suite locally.
The default nox, `verify-changed`, pre-push and `verify-completion` paths provide
targeted feedback. `verify` and full-suite lane commands are CI/CD entry points.

## Ground Control Context

This repo's Ground Control project id, workflow commands, and plan
rules live in `.ground-control.yaml` at repo root (with the full
plan rules set under `.gc/plan-rules.md`). Agents read it via the
`gc_get_repo_ground_control_context` MCP tool, which returns the full
workflow config in a single call.

Set `RAES_REQUIREMENT_UID` when the branch name does not already
contain a UID such as `GOV-918`.

The required repo-policy checks and hard rules are enforced by the
`/implement` skill through the plan rules file referenced in
`.ground-control.yaml` — see `.gc/plan-rules.md` for the authoritative
list.

## Repo skills

- Use `.codex-skills/raes-asset-inventory-capture/SKILL.md` from Codex. This
  server also links it at
  `~/.codex/skills/raes-asset-inventory-capture`.
- Use `.claude/skills/raes-asset-inventory-capture/SKILL.md` from Claude Code.
  This server also links it at
  `~/.claude/skills/raes-asset-inventory-capture`.
- Use `.codex-skills/raes-gap-remediation-implement/SKILL.md` from Codex when
  remediating RAES/APTL gaps found by the asset-inventory methodology. This
  server also links it at
  `~/.codex/skills/raes-gap-remediation-implement`.
- Use `.claude/skills/raes-gap-remediation-implement/SKILL.md` from Claude
  Code for the same overlay. This server also links it at
  `~/.claude/skills/raes-gap-remediation-implement`.
