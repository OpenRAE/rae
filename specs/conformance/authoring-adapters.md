# Authoring-adapter conformance v1

ASR-516 defines finite consistency evidence across authoring paths. A path can
be a CLI, agent, MCP tool, graphical editor, documentation workflow, or another
consumer. Path identifiers describe observations; they confer no authority.

## Published contract

The `authoring-adapter-vector/v1` descriptor binds a synthetic UTF-8 SDL source
by SHA-256, a closed operation by RFC 8785 SHA-256, a profile by RFC 8785 SHA-256,
and an expected observation. All defaults are materialized before hashing
contract models. Raw source hashes include every byte. The vector digest binds
the entire admitted descriptor, including its fixed expected observation.
A vector may also carry a fixed `contrast`: an alternative output source with
expected canonical-artifact and semantic dispositions. Consumers submit it as
the second path's output to verify that a meaningful difference is detected.
Contrasts have the same byte ceiling as ordinary outputs.

The `raes-authoring-adapter-conformance/v1` profile selects strict `sdl-yaml/v1`,
rejecting migration, normalized authoring artifacts, `raes-sdl-semantic/v2`,
and the exact digest of the existing semantic comparison profile. Operations
are `validate-sdl/v1` and `rename-sdl-declaration/v1`; the latter binds exactly
one canonical target and new local name. Rename uses the existing default
loss policy. Validation produces no transformation report.

The published JSON Schemas under `contracts/schemas/authoring-adapters/` define
closed shapes. Admission also checks source, operation and profile digests;
outcome/artifact consistency; sorted unique report reasons; and the existence
of semantic companion evidence for two successful observations. Schema
acceptance alone cannot establish these contextual facts.

## Submission and evidence

A consumer supplies each path's exact input source, output source or refusal,
incumbent structured diagnostic carriers, and any existing
`artifact-transformation-report/v1`. The reference API recomputes identity by
parsing output through the production structural and semantic gates. It never
accepts a claimed artifact digest or a private validation flag as evidence.

A successful observation records both the owning SDL canonical digest and the
existing semantic comparator's artifact coordinate. These are distinct
profile-labelled projections and must not be interchanged. A refusal has no
artifact and requires structured diagnostics. A transformation report must
bind the input source, output digest, owning profiles and outcome. Its full
canonical report digest remains independently compared with the fixture oracle.
Two identical incorrect results do not conform merely because they agree.

Selecting rename does not prove that transformation ran. A structured source
admission refusal has no artifact or transformation report. The runner must
recheck that the input fails strict admission before accepting this absence.
After source admission, both successful rename and transformation-level
refusal require the owning transformation report.

The diagnostic evidence digest is RFC 8785 SHA-256 over an object containing
`profile: authoring-diagnostic-semantics/v1` and `keys`: the sorted multiset of
four-string arrays. For `DiagnosticModel`, each array is
`[domain, code, severity, address]`; for `SDLParseDiagnostic`, it is
`[stage, code, severity, pointer]`. Multiplicity matters. Human message text,
source identities, and source ranges are excluded from this profile's equality
claim. Messages remain bounded to 512 UTF-8 bytes. Original diagnostic carriers
remain with the consumer for review; the portable report contains only their
semantic evidence digest. This projection does not define a new diagnostic DTO.

The v1 profile cannot certify unstructured semantic-error/advisory prose. Such
input or output requires a richer governed diagnostic profile; the runner must
fail closed. Inputs are self-contained: module imports, expanded artifacts and
materialized artifacts are outside this profile. No resource locator is fetched.

## Independent dispositions

`authoring-adapter-comparison/v1` reports canonical artifact, diagnostics,
transformation provenance and semantic relations independently as `equivalent`,
`different`, `incomparable`, or `not-applicable`. Missing or invalid observations
make every axis incomparable. Success versus refusal is an explicit outcome
difference. Two refusals have no artifact or semantic comparison; absent
transformation reports are not applicable. A changed provenance digest remains
a visible difference even when artifact semantics agree.

For two successful outputs, the existing semantic comparator receives the
admitted artifacts and their exact two-sided impact scope. Its complete
`semantic-comparison-result/v1` is companion evidence, bound by the comparison
report's digest. Unknown semantic relations, incomplete dependency context or
exhausted limits are incomparable. `representation-evidence-missing` alone does
not make the semantic axis unknown: v1 makes no exact-text assertion. The
companion result retains that reason and its original completeness unchanged.

A finite case conforms only when both observations match the checked-in oracle
and every axis is equivalent or not applicable. No universal, behavioral,
runtime, evidence, pack, or task-completion equivalence follows. The API records
successful production admission only; it issues no stronger validation-basis
disclosure or authenticated adapter attestation.

## Bounds and determinism

Vectors use at most 128 KiB of JSON; profiles use at most 16 KiB. Source and
output each use at most 64 KiB. A case carries at most 64 diagnostics and a
transformation report of at most 64 KiB. A corpus has 1–32 vectors, in case-id
order. JSON ingress rejects duplicate members and non-finite numbers. Corpus
files must resolve beneath the selected corpus directory.

The fixed SDL parser ceilings are 65536 input/scalar bytes, depth 32, 4096
nodes, 32 aliases, 8192 expanded/composed nodes, 65536 composed bytes, and
import/composition/namespace ceilings of 1. Imports remain inadmissible in this
profile. Limits and defaults are part of this versioned operation, not ambient
configuration. Comparisons have no clock, random, environment, network,
subprocess, persistence or logging inputs. Reports never copy source bodies or
exception text.

Normative vectors live in `contracts/fixtures/authoring-adapters-v1/cases` and
ship with the contract corpus. Expected observations are fixed publication
artifacts, not recomputed test oracles. Hub owns cross-product acceptance;
env-packs owns pack behavior; conformant backends own runtime outcomes.
