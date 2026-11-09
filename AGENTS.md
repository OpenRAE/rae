# RAES SDL agent rules

Use the repo policy tooling before and after implementation work.

Run only targeted tests locally. Full test, integration, fuzz and completion
suites run in CI/CD only, including after synchronization or reviewer fixes.
Use explicit relevant pytest modules/cases or `verify-fast-feedback`. Missing
change classification is never permission to run the full suite locally.
The default nox, `verify-changed`, pre-push and `verify-completion` paths provide
targeted feedback. `verify` and full-suite lane commands are CI/CD entry points.

## Ground control context

The Ground Control configuration is in `.ground-control.yaml` at the repository
root. The full plan rules are in `.gc/plan-rules.md`. Use the
`gc_get_repo_ground_control_context` MCP tool to read both in one call.

If the branch name has no UID such as `GOV-918`, set `RAES_REQUIREMENT_UID`.

The `/implement` skill uses these plan rules to enforce repository policy.
See `.gc/plan-rules.md` for the required checks and rules.

## Repo skills

For documentation, use the existing
[documentation style guide](docs/explain/reference/documentation-style-guide.md).
It gives the clean setup, changed-path checks, Diataxis purposes, and STE review.
Compare each claim with code at the specified revision. Keep technical meaning,
normative obligations, legal text, and pinned evidence. Record sources and results
in the PR.

Vale checks style. It does not show accuracy or full STE conformance.

Use the pinned `OpenRAE/doc-tools` documentation skill and the existing local
guide. The guide gives its release source and normal agent installation routes.
Checks need no personal skill installation.
Do not copy a personal skill or add a custom tool without approval.

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
