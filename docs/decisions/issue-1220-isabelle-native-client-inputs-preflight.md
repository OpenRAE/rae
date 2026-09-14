# Issue #1220 Isabelle native-client inputs preflight

Date: 2026-09-14

Issue: #1220. This is a requirement-free maintenance run. Its GitHub issue,
accepted ADR-106/ADR-107, and the accepted package-artifact design set are the
implementation contract. This note fixes architecture guardrails only; it does
not implement the migration or claim qualification evidence.

## Entry gates and ownership

Before execution, assign the named Proof/Tooling implementation owner and
verify in the live GitHub graph that #1168 and every native blocking
prerequisite of #1220 is satisfied. A prose dependency reference, merged
design, or cache hit is not a substitute. The implementation records the
result against the existing qualification-record authority, with exact commit,
tool/platform/policy identities and evidence location.

## One authority path, two distinct boundaries

| Concern | Canonical incumbent | Guardrail |
| --- | --- | --- |
| Artifact/policy selection | `implementations/tooling/artifacts.lock.json`, `admission-policy.json`, `profiles/development-profiles.json`, schemas, and `tools/check_tooling_artifact_policy.py` | Select Isabelle only through `load_tooling_artifact_selection()`, before any cache, local input, installation, or replay. Preserve its exact 1,228,480,874-byte raw object, SHA-256, canonical platform, approved same-byte locators, policy refs, and profile. Do not copy these into proof code or tests. |
| Native raw carrier | `tools/maintained_client_acquisition.py` and its qualified curl process in `tools/bootstrap_profile.py` | Consume only admitted bytes from this boundary or an explicit lock-verified local raw input. No `urllib`, HTTP client, retry/failover, redirect, TLS, proxy, framing, status/header parsing, or transport exception classification may remain in Isabelle code. Isabelle's large-object size/time budget is a separately qualified selection/configuration seam, not a generic-CLI default. |
| Installed-tree admission | `tools/verified_tool_installation.py`, `LockedArtifactSelection`, `LockedManifestEntry`, and #1219's private-root/atomic-publication contract | Reuse one complete installed-tree validation/publication path. The installation identity binds artifact, canonical platform, raw digest, installation-policy identity, and the canonical installed manifest. Validate/reconstruct from the admitted archive; executable existence and the sidecar archive marker are never trust evidence. |
| Proof execution | `tools/isabelle_tool.py`, `tools/isabelle_sandbox.py`, `tools/check_participant_opacity_proof.py`, and #1109 | Keep the fixed Linux x86_64 proof boundary, resource limits, Bubblewrap network namespace, minimal environment, private state, and allowlisted runtime/session mounts. Installation does not broaden sandbox exposure. |
| Workflow/evidence | ADR-014, `noxfile.py`, `SessionReporter`, `bootstrap-qualification.yml`, `canonical-verification.yml`, and `development-profiles.json` qualification records | Extend the existing required graph and record T01/T05/T08/T11/T13 there. Do not add an Isabelle-only workflow, evidence schema, or reporter. |

The raw archive and installed tree are different propositions: the former is
the selected input; the latter is a derived, fully verified local
materialization. Do not conflate either with the proof evidence manifest's
`archive_url`: that field remains reproducibility provenance constrained to an
approved locator, while the lock/profile selection is the acquisition
authority. Any change to digest-bound proof-tool sources or their evidence
representation must update the existing proof-evidence validation/digests as
one reviewed evidence change, not bypass it.

## Cross-cutting security and operating layers

| Layer | Required treatment |
| --- | --- |
| Repository/config shape | Reuse Git-tracked regular-file confinement, bounded JSON loading, closed Draft 2020-12 schemas, platform/profile normalization, selector bindings, locator/secret checks, and `PolicyFailure` aggregation. If archive format/member/count/decoded-size bounds need authority, extend the existing closed artifact-lock schema and project it through `LockedArtifactSelection`; no second manifest or validator. |
| Secrets and authentication | The public proof profile is credential-free. Preserve policy rejection of locator user-info, interpolation, and secret-bearing query fields. Do not add headers, netrc, token files, signed locators, or enterprise fallback. |
| OS/process exposure | The maintained client uses fixed argv, closed stdin, minimal environment, private output, and a wall deadline. Never put a token, header, secret path, shell fragment, or untrusted executable path in argv. Replay keeps `--clearenv`, fixed locale, private state/temp, read-only qualified installation/session/runtime paths, and network isolation; host roots, home, workspace, and mutable cache roots remain unbound. |
| Filesystem/persistence | Use #1219's private owned roots, native lock with bounded wait, same-filesystem private staging, no-follow/opened-inode validation, complete archive admission, immutable mode, fsync, atomic directory rename, reopen/revalidation, and lock-held crash recovery. Unsupported NFS/SMB/FUSE/unknown durability semantics fail explicitly. A read-only seed/local input is an explicit carrier, revalidated and copied into private staging, never a discovered fallback. |
| Errors/observability | Static violations remain `PolicyFailure`; operational install/acquisition/replay failures remain sanitized existing tool-boundary errors and `SessionReporter` stage records. Do not create an Isabelle installation exception hierarchy or misuse proof/scanner result types. Record logical artifact/platform/policy, cache outcome, bytes, duration, lock wait and stable reason only; redact native stderr, archive content, paths, locators, environment, and secrets. |
| Host dependency closure | The selected proof host must carry Bubblewrap, fontconfig, at least one font, C.UTF-8 locale, and the #1109 conditional fontconfig/runtime allowlist. These are reviewed native prerequisites/export-closure inputs, not files asserted to be contained in the Isabelle archive. Missing dependencies fail before execution and never cause an unisolated replay. |

## Extensibility seam and verification boundary

The seam is the validated `LockedArtifactSelection`, an explicit raw carrier,
an explicit qualified private installation root, and a closed installation
policy/format-bounds identity. A later multi-file prover tree, larger admitted
archive, qualified immutable seed, or revised profile changes reviewed lock or
profile data (and, where necessary, one fixed archive adapter); it does not
add Isabelle URL conditionals, a bespoke cache layout, marker protocol, or
second lock.

The required evidence is T01, T05, T08, T11, and T13 on Linux x86_64. T05 must
exercise real concurrent Isabelle installers and publisher-kill durability
points; T08 must exercise the real qualified commodity client (its test-only
fixture is not production transport); T11/T13 must preflight the archive plus
fonts/locale/Bubblewrap closure on an egress-blocked clean target without
executing missing or malicious inputs. Unsupported operating systems or
architectures fail explicitly before acquisition/installation/replay and are
not a skip or a successful proof claim.

## Gotchas, anti-patterns, and non-goals

- Do not retain `urlopen`, `urllib`, custom mirror loops, shared `.download`
  files, `extractall` without complete prior archive admission, version-only
  paths, executable-exists checks, or marker-only installed-tree trust.
- Do not silently delete/reacquire after raw, archive, installed-tree, seed,
  or cache integrity failure; quarantine/record the failure and require a new
  explicit repair invocation. Do not make an integrity failure an availability
  fallback.
- Do not weaken the current sandbox resource limits or introduce host-network,
  host-home, broad workspace, ambient-environment, or writable shared-cache
  exposure to make installation or replay convenient.
- Do not alter proof/theorem semantics, archive identity, source policy,
  supported platform scope, Python resolution, native OS package management,
  promotion/release admission, offline-bundle format, or repository-wide
  transport migration. This issue owns only the Isabelle raw-carrier and local
  installation cutover plus its required closure/evidence.
