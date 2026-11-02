# Issue 1858: Go verification inventory preflight

Issue #1858 is the delivery contract.
ADR-106, ADR-121, and ADR-122 govern this change.
No new ADR or product contract is needed.

## Authority and ownership

`implementations/architecture.json` is the only declared Go module list.
Each module has a directory and module path.
Its display name and category do not define its identity.
The existing `arch` package owns model parsing and module discovery.
Reuse `Load`, `CheckDesign`, `LoadCode`, and `CheckCode`.
Do not add a second discovery method or architecture schema parser.
Keep the existing exclusions for `testdata`, dot prefixes, and underscore prefixes.
Keep nested module discovery.
A design declaration may precede code. CI still needs the declared module files.

Derive consumers from checked modules or require exact agreement with the model.
Reject missing, extra, and duplicate entries.
Equal counts alone do not prove coverage.
Python adapters may read module directories after `archcheck` succeeds.
They must not interpret the rest of the architecture model.
Any new Go API still needs the model design check before implementation.

Product and tooling remain separate dependency closures.
Build tools through the tooling module. Run each gate within each target module.
Neither category can disable a gate.
Do not import product internal packages into tooling.
Do not add model fields for display names or lane exemptions.

## Required checks and consumers

- Each module needs compiler, dependency, lint, analyzer, race test, coverage, fuzz, mutation, and regression checks.
- Keep the 90% coverage floor for each module.
- Keep numeric mutation thresholds and module-relative diff paths.
- Keep the existing regression replay and comparison-base checks.
- Use explicit shared lint configuration at any module directory depth.
- Keep exact source SHA checkout and stable required status names.
- Fail the aggregate gate on a failed, skipped, or cancelled producer.
- Reconcile matrix rows, coverage uploads, Sonar downloads, report paths, and analyzed roots.
- Missing or invalid coverage must fail even when Sonar is disabled.
- Each artifact name must identify its module without collisions.
- Do not flatten different module profiles onto one `cover.out` path.
- Reconcile OSV Go targets and report uploads. Keep both Python lock targets.
- Require every expected scan report on success. Keep available reports on failure.
- Preserve networked scanning in the separate supply-chain job.
- Keep release callers on the same canonical verification graph.

## Security boundaries

The protected asset is the CI verdict.
An omitted module can bypass the compiler or dependency scanner.
The module check must reject that omission before CI can pass.
Pull request files are untrusted inputs.

Use the closed workflow parser in `implementations/tooling/action_policy_yaml.py`.
It rejects aliases, duplicate keys, and malformed scalar values.
Use bounded JSON and path containment helpers from `tools.policy.common`.
Do not follow paths outside the checkout, including through symlinks.
Do not treat an invalid or empty inventory as success.

Keep the admitted archive checks in `bootstrap_profile` and the tool locks.
Do not add a downloader or automatic tool installation.
Use `GOTOOLCHAIN=local`, `GOFLAGS=-mod=readonly`, and `GOWORK=off` for Go commands.
Keep `go mod tidy -diff`, `go mod verify`, and reviewed dependency sums.
Do not let a newer module toolchain trigger an automatic download.

Keep read-only tokens, immutable action pins, and `persist-credentials: false`.
Preserve the exact Sonar trust condition and token binding.
Never run new inventory code with the Sonar token.
Use fixed argv and quoted environment bindings for commands.
Never splice module strings into shell source.
Validate artifact names and single-line Actions outputs.
Do not print malformed document contents, environment maps, or credentials.

Reuse existing error types and reporting.
Invalid inputs must fail with an actionable location and fix.
Reuse the OSV installer, scanner, and exit classification.
Both vulnerability findings and scanner errors must block CI.
Keep JSON reports separate from progress messages.

No product controller, runtime store, schema, or environment-pack change is needed.
No new hosting, database, service, or persistent module registry is needed.

## Extension and evidence

The extension seam is the checked collection of module identities.
A third module must reach every gate and artifact consumer.
A retained consumer list must fail until it agrees with that collection.
Keep one common lane policy without module exemptions.

Add negative fixtures for a new modeled module missing from CI or scanning.
Test coverage omission, duplicate identities, unsafe paths, and missing lanes.
A declared same-layer cycle must pass architecture checks, then fail compilation.
A missing dependency or broken fixture does not prove cycle rejection.
Keep fixtures in temporary repositories or `testdata`.
Run focused tests locally. Full module, fuzz, and mutation verification stays in CI.

Keep compiler cycle detection in Go.
This change proves module inclusion, not compilation for every OS and build tag.
Do not change coverage floors, dependency versions, merge gates, or product behavior.
Do not claim success from a matrix row, wildcard upload, or combined coverage alone.
Fail explicitly on resource limits instead of dropping modules.
