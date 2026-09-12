# Issue #839 Action Input Admission and Scorecard Preflight

Date: 2026-09-11

Issue: #839. Requirement: GOV-913 (MUST, Wave 3). The issue title, body,
acceptance criteria, the existing GOV-913 specification and ADR-071, accepted
ADR-106/ADR-107, and the accepted package-artifact design set are the
implementation contract.

This note records architecture guardrails only. It does not change workflow
behavior, admit an action or payload, execute T04/T08/T10/T23, record a
successful Scorecard run, or authorize a README badge.

## Current boundary and findings

The tracked baseline has ten workflow files, 60 external action use sites from
14 action families, and two local calls to `canonical-verification.yml`.
`implementations/tooling/actions-policy.json` v1 owns each action family's exact
commit, owner roles, and Git trust root. The existing action validator discovers
all tracked workflow `uses` values and rejects mutable, unowned, and stale
sources. It does not yet model or check action-internal payloads and services,
individual use sites, action inputs/defaults, events, effective permissions,
checkout credential persistence, runner prerequisites, allowed origins,
credential flow, cache/artifact trust, or Dependabot policy.

Existing selector policy already binds the exact CPython and uv payload versions
used by `actions/setup-python` and `astral-sh/setup-uv` to
`artifacts.lock.json`. Action admission must join that authority rather than
copying those versions or digests. Inline workflow acquisition remains covered
by `tooling_artifact_policy_discovery.py` and `inventory-coverage.json`; it is
not action-transitive input merely because it appears in a workflow.

The implementation must resolve these current security gaps rather than merely
expanding the JSON inventory:

- PR-executed `ci.yml` jobs without a job-level override inherit the workflow's
  `pull-requests: write`, although no current CI step needs it. Fork token
  downgrading is not a substitute for an explicit untrusted-job boundary.
- The Sonar job excludes forks and Dependabot but supplies `SONAR_TOKEN` while
  consuming a same-repository PR checkout and configuration. Any PR head is
  candidate input; enterprise credentials must be confined to protected-branch
  execution or an equivalently protected workflow/policy boundary.
- `ci.yml`, `scorecard.yml`, and `release-please.yml` accept manual dispatch.
  Their privileged jobs do not all prove that the selected workflow definition
  is the protected revision: CI's non-PR condition admits the Sonar secret,
  Scorecard has security-event and OIDC writes, and release has publication
  authority. A maintainer-triggered dispatch is not itself a trusted source-ref
  proof; privileged paths must fail unless the workflow and policy revision are
  protected.
- Most checkout use sites accept the default persisted token. Jobs that do not
  require Git authentication after checkout must set and mechanically retain
  `persist-credentials: false`; later API calls use their explicitly scoped
  environment token.
- Action-owned caching must be inventoried even when no explicit
  `actions/cache/save` step exists. An omitted action input or action default
  must not allow untrusted work to populate a cache later trusted by a
  privileged job. The explicit Isabelle restore-only use is the incumbent safe
  cross-context pattern.
- `scorecard.yml` uses the moving `ubuntu-latest` label and a broad top-level
  `read-all` default. Its job-level permissions are explicit, but the workflow
  should use the fixed selector owned by a #1217 host profile and a
  deny-by-default workflow permission baseline while retaining the exact
  reporting permissions. The current #1217 qualification records are
  `not-run`; a declared profile must not be called qualified until measured
  delivery-revision evidence passes.
- The current Scorecard regression repeats a source SHA but does not establish
  the weekly schedule, transitive closure, runner profile, egress mode,
  successful live run, or README badge. The README currently has no Scorecard
  badge; repository state alone contains no successful service-run evidence.

Every tracked workflow is in scope. Their intended trust boundaries are:

| Workflow | Trust and privilege boundary to preserve or repair |
|---|---|
| `bootstrap-qualification.yml` | PR/manual candidate execution is read-only and may publish run-scoped untrusted evidence, never trusted cache or promotion state |
| `canonical-verification.yml` | Local reusable exact-ref verification is contents-read, restore-only for shared Isabelle cache, and may execute candidate code without secrets |
| `ci.yml` | PR jobs are untrusted and read-only; protected pushes may run service jobs, but Sonar credentials must not cross into PR-controlled input |
| `docs.yml` | PR build is read-only; Pages artifact upload and OIDC deployment are restricted to the protected `main` context |
| `pr-title-lint.yml` | Read-only PR metadata flow executes the base-ref checker; untrusted title/body/commit text stays out of shell interpolation |
| `pr-body-policy.yml` | Read-only PR metadata flow executes the base-ref checker and uses only the job token's read scopes |
| `post-merge-closing-issue-audit.yml` | Merged-only audit checks out trusted `dev` and has read-only repository/issue/PR access |
| `python-free-threaded-preview.yml` | Scheduled/manual protected workflow is read-only and advisory; it cannot satisfy blocking interpreter support |
| `release-please.yml` | Protected `main` execution keeps orchestration, exact-SHA verification, unprivileged build, PyPI OIDC, and GitHub finalization separated; manual dispatch additionally proves its workflow/policy ref is protected |
| `scorecard.yml` | Protected branch/schedule/push execution retains explicit Scorecard publication, SARIF upload, and audit-mode egress without PR secrets; manual dispatch is permitted only from the same protected definition |

## Authority and concept boundaries

| Concern | Canonical incumbent | Guardrail for #839 |
|---|---|---|
| Ecosystem reusable-asset trust | `specs/supply-chain/reusable-asset-trust-integrity.md`, `reusable-asset-trust-policy-v1`, ADR-071, and `test_reusable_asset_trust_policy.py` | Treat action-input admission as developer/delivery supply-chain enforcement contributing to GOV-913; do not add a workflow/action family to the portable reusable-asset contract or reuse that contract as an action inventory |
| Action source identity | Literal full commit in every `.github/workflows/*.yml` use and `implementations/tooling/actions-policy.json` | Keep the workflow literal executable selector and the policy its reviewed admission record; comments/tags are labels, never trust roots |
| Action-transitive payload identity | `implementations/tooling/artifacts.lock.json`, its closed schema, and `admission-policy.json` | Reference an existing or newly admitted artifact/OCI identity; do not embed a second payload manifest, Python graph, or digest authority in action policy |
| Python and bootstrap payloads | `implementations/python/uv.lock`, `selector-bindings.json`, and #1217's locked CPython/uv records | Keep action source commit, interpreter/uv bytes, Python dependency resolution, and host qualification as separate joined identities |
| Action source-to-payload closure | The existing `actions-policy.json` and `actions-policy.schema.json` | Evolve this authority atomically to describe every exact source revision's internal payload, service, runner, origin, and exception closure; do not create a parallel action inventory |
| Host and runner prerequisites | `profiles/development-profiles.json`, `profiles.schema.json`, and #1217 qualification evidence | Join each workflow job to a closed host profile and required capabilities, with the workflow runner selector mapped in that existing profile authority. A runner label, profile declaration, action runtime declaration, installed CLI, daemon, and passing observation are distinct |
| Workflow job and use-site security | Workflow event/job/step literals plus the action policy's normalized workflow projection | Check source/ref trust class, effective permissions, runner profile, effective environment/secret references, ambient token classes, origins, and cache/artifact read/write role for every job, then inputs/defaults and closure for every action occurrence |
| Local reusable workflow identity | `canonical-verification.yml`, its `workflow_call` input contract, exact-SHA checks, and focused release tests | Validate the local path, callable contract, caller source/ref rule, permissions ceiling, inputs, and call sites. A local path alone is not protected source identity |
| Inline acquisition and tools | `tooling_artifact_policy_discovery.py`, `inventory-coverage.json`, `selector-bindings.json`, and the owning artifact lock | Preserve the current cross-repository discovery gate. #839 adds action-internal closure and must not absorb #1218, #1137, or later cache/OCI migrations |
| External service-managed inputs | S02 in the package-artifact inventory and reviewed exception records in action policy | Record the inability to pin, owner/reviewer roles, exact scope, allowed origin, credential behavior, review evidence, and expiry/review date. Do not fabricate a digest or fake artifact row |
| Permissions and credentials | Literal workflow/job `permissions`, GitHub events/environments, `GITHUB_TOKEN`, Actions runtime/cache/artifact tokens, OIDC, and the Sonar secret boundary | Store only permission names and credential reference classes. Assume an action can reach the job token and service tokens allowed by its context even when no `token` input is present; secret values never enter Git, and possession does not admit bytes |
| Caches, artifacts, Pages, and SARIF | Existing cache restore, artifact handoff, Pages, Scorecard, Sonar, and release workflow invariants | Classify producer trust, run/repository scope, read/write ability, consumer, retention, and whether content is evidence or authority. Names and cache keys never establish integrity |
| Release and publication | ADR-107, `release-please.yml`, `canonical-verification.yml`, and `test_release_workflows.py` | Preserve exact-SHA/ancestry checks, read-only candidate verification, same-run handoff, protected PyPI environment/OIDC, and separate GitHub publication. Action admission supplements these gates |
| Scorecard public evidence | `scorecard.yml`, `test_public_project_readiness.py`, root `README.md`, and official GitHub/Scorecard services | Preserve cron `17 3 * * 1`, SARIF plus code-scanning publication, `always()` uploads, five-day artifact retention, and harden-runner's explicit audit egress. Add the badge only after a successful recorded run and render check |
| Dependency updates | `.github/dependabot.yml`, `artifacts.lock.json`, and the governed Z3 solver profile | Keep weekly GitHub Actions/Python proposals targeting `dev`. A bot source bump must fail admission until human-reviewed source and payload closure agree; Z3 remains excluded from ordinary updates |
| Errors and observability | `PolicyFailure`, `failures_to_json()`, `SessionReporter`, native action annotations, and SARIF | Extend stable deterministic findings; do not add an exception hierarchy, workflow logger, result DTO, or raw-response diagnostic surface |
| Persistence | Reviewed Git policy plus GitHub run/artifact/code-scanning evidence | No application database, controller, service, repository, runtime DTO, or portable SDL contract participates in this change |

## Closed action-policy contract

Keep one versioned action-policy document and one validator. If the v1 shape is
incompatible, advance its internal schema version; do not silently redefine v1.
The policy has three separate planes:

1. **Source records** bind one action family to its exact commit, owner/reviewer
   roles, source-review evidence, and action runtime kind.
2. **Transitive-input closure** binds that exact source record to every internal
   input. Each input has exactly one disposition: a reference to an admitted
   payload/OCI record, a reference to a #1217 runner capability, or a reviewed
   service-managed exception. An explicit reviewed empty closure is different
   from an omitted or unknown closure.
3. **Workflow job contexts and use sites** bind every discovered job, including
   jobs with only `run` steps, to its event/ref trust class, protected-definition
   requirement, effective permission set, runner profile, effective
   workflow/job/step environment and secret-reference classes, ambient token
   classes, allowed-origin set, and cache/artifact role. Each action occurrence
   then binds its literal inputs and security-relevant defaults to that job
   context and its source closure. The structured parser supplies the occurrence
   identity; an explicit step `id` is required where a job would otherwise have
   ambiguous repeated uses.

The transitive graph must be closed and acyclic. Every payload reference joins
the owning lock and admission policy; every runner capability joins a selected
host profile; every exception joins exactly one source revision and internal
input. Unknown dispositions, unresolved joins, an unreviewed source change, an
extra workflow use, an undeclared action default, or a stale record fail
qualification. Policy data remains inert: no action metadata may contain shell,
argv, environment expansion, executable hooks, download options, or arbitrary
probes.

A service-managed exception is a bounded nonclaim, not admission. It records a
stable id, source action and commit, input/service identity, why byte pinning is
not available, permitted origins and operation, credential class and forwarding
rule, owner and independent reviewer roles, evidence reference, scope, and an
expiry or review date. Deterministic static validation checks the record and
joins without consulting the wall clock; expiry evaluation receives an explicit
trusted UTC evaluation instant. Do not use `tools/policy/exceptions.yaml` to
hide an uninventoried transitive path.

## Reused validation and workflow layers

All changes continue through the existing fail-closed path:

1. `safe_repo_path()`, regular-file/no-symlink checks,
   `load_bounded_json_object()`, the two MiB bounds, UTF-8 parsing, and
   duplicate-key rejection run before policy interpretation.
2. The project-locked Draft 2020-12 validator checks the closed internal schema
   with local fragment references only. Action policy stays under
   `implementations/tooling/`; it is not registered as a published contract.
3. `tooling_artifact_policy_actions.py` extends the existing semantic layer for
   source, closure, use-site, permission, runner, origin, credential, reusable
   workflow, and Dependabot joins. `check_tooling_artifact_policy.py` remains the
   single entry point and `tooling_policy_sha256()` remains the complete policy
   binding.
4. Tracked-file enumeration remains NUL-delimited `git ls-files`; workflow YAML
   continues through one hardened version of the incumbent PyYAML structured
   parser. It must retain the two MiB source bound, reject duplicate mapping
   keys, recursive/unsupported alias or merge shapes, and non-mapping roots, and
   normalize PyYAML's YAML-1.1 treatment of GitHub's literal `on` key before
   event validation. Matrix runner values must resolve to a closed set, dynamic
   `uses` remains prohibited, and a new workflow, expression, or syntax that the
   extractor cannot classify fails closed. Security conclusions never come
   from regex matches over raw YAML.
5. `tooling_artifact_policy_discovery.py`, `inventory-coverage.json`, and
   `selector-bindings.json` continue to own inline acquisitions and selector
   drift. Their exact occurrence coverage must not degrade into “the right
   literal exists somewhere in this file.”
6. `tools/nox_support/policy_lanes.py`, the canonical Nox graph, hooks, CI, and
   Ground Control remain the invocation/observability path. Every workflow and
   `.github/dependabot.yml` must enter the existing tooling-test trigger class;
   do not special-case only `ci.yml`.
7. Focused Scorecard and release tests retain stronger domain invariants, but
   source/payload lists come from the single policy authority. Do not maintain
   a second exact-SHA catalog in tests.

Action execution occurs before repository Python can validate the action that
bootstraps a job. The repository gate therefore cannot, by itself, prevent the
GitHub runner from fetching an unapproved action. GitHub Actions allow-policy,
protected branch/ruleset and environment configuration are external enforcement
layers and require recorded evidence. A PR-owned workflow check is useful drift
evidence, not a substitute for that platform gate or review-protected privileged
workflow definitions.

## Security and information-flow guardrails

- **Authentication/authorization:** Public and PR jobs use no enterprise
  credential, promotion token, publication permission, or trusted cache-write
  authority. Give every job the minimum explicit permission map. Treat the
  scoped `GITHUB_TOKEN`, Actions artifact/cache service tokens, and OIDC minting
  endpoint as ambient authority available to third-party code according to the
  job context, not only when a workflow has an explicit token input. Privileged
  jobs run only from the protected workflow/policy revision and revalidate the
  exact admitted source/artifact identity before using GitHub write or OIDC.
- **Secret handling:** Reuse `has_secret_bearing_locator()`, Gitleaks, and
  private-key detection. Policy stores credential classes/references only and
  rejects URLs with user info, signed queries, headers, interpolation, tokens,
  inline CA/key material, or arbitrary environment maps. A maintained action or
  CLI receives a secret through its supported protected input/environment/file
  channel, never argv, checkout config, cache key, artifact, evidence, or public
  log. Cross-origin forwarding is deny by default.
- **Configuration shape:** Events, ref restrictions, expression shapes,
  workflow/job permission inheritance, matrices, `with`/`env` overlays,
  reusable inputs/secrets, runner selectors, and Dependabot groups pass the
  structured semantic validator. `secrets: inherit`, unknown permissions,
  `write-all`, `pull_request_target`, privileged dispatch without a protected
  ref, mutable runner aliases, implicit public fallback, and secret-bearing PR
  jobs fail closed unless a narrower existing contract proves them safe.
- **OS/process exposure:** #1217 host profiles own Git, GH, CA, hash, curl,
  interpreter, uv, proof, container, and daemon capabilities. Action policy
  references them; it does not execute host inspection or provisioning.
  JavaScript, composite, and Docker actions are separately classified because
  they execute on different runner/process surfaces while sharing the workspace
  and job authority. Tokens do not enter process argv. No validator receives a
  daemon socket, elevated privilege, broad ambient environment, user config, or
  network access.
- **Error envelopes:** Emit sorted `PolicyFailure` rule ids with repository
  paths and logical source/use/input ids. Do not print policy documents, full
  locators, action output, native stderr, response bodies, credential refs,
  private package names, environment values, or GitHub event payloads. Live
  workflow evidence uses native annotations/SARIF and bounded run references.

## Qualification and evidence boundaries

- **T04** must mutate an action source, internal input, permission, checkout
  persistence, cache role, workflow trust class, manual-dispatch ref guard,
  install hook, explicit credential declaration, and ambient-token
  classification independently. Static cases prove fail-before-acquisition; an
  actual fork run records that no private credential/write/promotion/publishing
  authority is available and that its artifacts/caches cannot authorize a
  privileged consumer.
- **T08** reuses the #1217 real-curl fixture and host-profile evidence. Do not
  create an action-specific HTTP harness or treat an action's successful setup
  as curl qualification.
- **T10** exercises missing authentication, wrong digest, 401/403, mirror-only
  no-fallback, and cross-origin credential non-forwarding through maintained
  clients or test-only endpoints. The result is scoped evidence; it does not
  claim that an enterprise repository, Simple API, registry, or provider has
  been deployed or qualified.
- **T23** extends the existing temporary-repository policy tests so independent
  source, payload, service exception, use-site, runner, permission, origin,
  reusable workflow, Dependabot, and acquisition-path drift all produce stable
  failures before any cache or network function is reached.

Changing action policy changes `tooling_policy_sha256()`. Existing #1217
qualification evidence bound to the previous complete policy is stale by
design. Do not copy a new hash onto old observations or weaken the hash scope;
rerun the applicable evidence, including the required T08 regression, against
the delivery revision and record outcome, run id/attempt, exact source SHAs,
payload identities/digests, policy hash, runner image, permissions, and evidence
location in the issue/PR.

Scorecard acceptance additionally requires a successful scheduled or explicitly
identified equivalent run at the admitted revision, successful SARIF artifact
and code-scanning publication, recorded harden-runner audit/egress behavior, and
a public badge response/render check. Preserve the weekly cron and explicit
`always()` reporting. Add the README badge only after the external result is
live; a unit test, fabricated SARIF, manual screenshot, or checked-in “passed”
record is not service evidence.

Dependabot remains a proposal source, not an authority. GitHub Actions and
Python updates stay weekly and target `dev`; GitHub reads this configuration
from the default branch, so activation timing must be recorded honestly. An
action bump may update the workflow source selector, but it cannot auto-approve
the closure or exceptions. The `z3-solver` ignore and the separately governed
solver profile remain mechanically unchanged.

## Extensibility seam

The extension seam is one normalized workflow-job context carrying
`workflow_path`, `job_id`, event/ref trust class, protected-definition rule,
`host_profile_id`, exact effective permission set, effective credential/token
classes, allowed-origin profile, and cache/artifact role. Action occurrences
reference that context and their source identity. An action's internal inputs
independently use the closed union of `artifact_ref`, `host_capability_ref`, or
`service_managed_exception_ref`. Workflow runner selectors map to profile ids in
the existing development-profile authority rather than a second platform table.

A future workflow, reusable workflow, platform, action revision, payload,
registry, or enterprise credential adds a reviewed record and, only for a new
syntax, one extractor that emits the same normalized shape. It must not require
an action-specific validator, another action schema, duplicated platform table,
workflow-name conditionals, or an executable plugin escape hatch.

## Development-branch synchronization

The pre-PR synchronization with `dev` at
`8e6dbb742fb98d50bb16a55c47f941abd49ff58d` incorporated the maintained-client
acquisition boundary from #1137. Its new canonical-verification handoff is part
of the action-admission surface: the producer job disables checkout credential
persistence and setup-uv caching, uploads only the locked local inputs, and the
proof job consumes that same-run artifact. Both jobs and all five new or moved
action occurrences are admitted by the v2 workflow/use-site records, and the
qualification records bind the combined tooling-policy hash.

## Gotchas and anti-patterns

- Do not equate an action commit, release tag/comment, bundled action source,
  downloaded tool, container image, runner runtime, service response, or
  credential; each has a separate identity and trust decision.
- Do not conflate the portable GOV-913 reusable-asset family policy with the
  repository-internal development action policy. This issue enforces the same
  trust principles at a delivery boundary; it does not redefine reusable SDL
  asset families.
- Do not call a source-SHA inventory transitive closure. Audit composite steps,
  JavaScript runtime dependencies, Docker/base images, setup downloads, action
  caches, API/service calls, and security-relevant defaults at the selected
  revision.
- Do not duplicate CPython/uv payloads, Python packages, OCI identities,
  platform aliases, permission maps, action SHAs, or workflow occurrence lists
  across locks, tests, and comments. Join their canonical authorities.
- Do not trust a cache key, artifact name, same-run success, SARIF filename,
  service-provided checksum, mutable image tag, runner label, or action version
  comment as integrity evidence.
- Do not let fork-only token downgrading excuse write permissions or secret
  exposure to another PR class. Treat every PR head and its configuration as
  candidate input.
- Do not treat `workflow_dispatch` or a human initiator as proof that the
  selected workflow definition is trusted, or an absent `token:` input as proof
  that an action has no GitHub, cache, artifact, or OIDC authority.
- Do not let YAML duplicate keys, aliases/merges, PyYAML's boolean `on` key, or
  unparsed expressions create a second interpretation between GitHub and the
  validator. Unsupported ambiguity fails closed.
- Do not equate a host-profile declaration or a `not-run` record with successful
  runner qualification, and do not copy a new policy hash onto old evidence.
- Do not pass repository/enterprise credentials to checkout, Sonar, release,
  Pages, Scorecard, or another action unless that exact protected use is
  declared and least-privilege. Do not let credentials cross redirects/origins.
- Do not use a broad waiver, non-expiring unexplained exception, “no known
  downloads” boolean, stale source review, or fake digest to make closure pass.
- Do not auto-edit policy from Dependabot metadata, change the Z3 profile, weaken
  exact-SHA/release admission, publish from PR code, or add the Scorecard badge
  before live evidence.
- Do not add a custom action downloader, repository HTTP stack, retry loop,
  redirect/TLS logic, custom Actions runner, or vendored copy of every action.

## Non-goals and implementation boundaries

- No Python tool/build/smoke resolver work (#1218), generic transport migration
  (#1137), shared cache/install safety (#1219), OCI mirror/import (#1223),
  intake/distribution service (#1224), complete offline export (#1225),
  SBOM/provenance (#1226), durable release admission (#1227), or operations/DR
  qualification (#1228), except to preserve and reference their boundaries.
- No enterprise repository deployment, credential creation/resolution, GitHub
  organization purchase, production promotion, release, protected-branch merge,
  or feature-PR merge.
- No claim that GitHub-hosted Actions, GitHub cache/artifact/Pages/code-scanning
  services, Sonar, Scorecard result publication, OIDC, or Dependabot works
  offline. Disconnected execution reports these live controls unevaluated.
- No portable schema, SDL/runtime asset ontology, controller, DTO, service,
  repository, application authentication model, database, cache store, or new
  exception/logging hierarchy.
- No replacement of release-please, PyPI Trusted Publishing, the canonical Nox
  graph, existing Scorecard reporting/egress behavior, or GitHub's maintained
  action transport.
