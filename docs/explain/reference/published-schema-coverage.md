# Published-Schema Coverage

Every schema under `contracts/schemas/` is a normative published contract
(`ADR-009` §7). `tools/check_schema_publication.py` proves the *inventory*:
that the manifest and the tree agree, that each entry carries its stability
class and canonical content hash, that a stable schema evolves under
`ADR-061`, and that a removal leaves a tombstone. It does not ask whether
anything in the repository ever exercises the contract.

`tools/check_schema_coverage.py` asks exactly that, by schema path, over the
whole published inventory. It runs as the `policy / published schema coverage`
stage of `nox -s policy`, so it sees the full tree on every run rather than the
changed-file set — a coverage repair can be undone by a deletion, and
`changed_paths()` excludes deletions.

## The rule

A published schema is **covered** when at least one of these holds.

1. **Corpus coverage.** At least one checked-in artifact routes to that exact
   schema path through the canonical corpus router,
   `check_json_artifacts.covered_schema_paths()`. Those artifacts are precisely
   what the contracts lane validates, so the evidence is executable rather than
   declared. The set is non-empty by construction: an empty `valid/` directory,
   a family with only `invalid/` cases, and a bare directory are all *not*
   coverage.

2. **Formal coverage.** The schema path is a `delivered_artifacts` entry of a
   classified subsystem in `specs/formal/assurance-fulfillment.yaml` — usually
   as that subsystem's `typed_ir_or_contract_coverage`. A `waived_artifacts`
   entry never counts. A dated, tracked waiver records an unresolved
   obligation, and relabelling one as delivered coverage is the failure this
   distinction exists to prevent.

3. **Declared alternate coverage.** The contract's publication record carries a
   validated `coverage` association naming the concrete evidence that exercises
   it, for a contract neither canonical route reaches.

**A formal model is never required.** Leg 2 is one alternative among three. The
gate never reads an FM level, never infers FM applicability, and never turns a
missing formal association into "not applicable" — FM applicability belongs to
`specs/formal/assurance-policy.yaml` and `assurance-fulfillment.yaml` under
`tools/check_assurance_policy.py`. A structural contract passes on leg 1 alone.

The denominator is the publication catalog read through
`load_schema_publication_catalog()`: draft and stable entries alike, with
`removed_schemas` tombstones excluded. Evidence is evaluated against the
schema as it is checked in now, so a contract's coverage claim is re-derived
whenever the contract changes.

## Routing completeness

Leg 1 is only as honest as the router behind it. A checked-in document that
names a published contract but that no route reaches is the silent hole this
rule exists to close: the contract can read as covered elsewhere while that
document drifts out of conformance with nothing to catch it. So every corpus
tree that holds documents naming their own contract is a row in
`_VERSIONED_SCHEMA_ROUTES` — the profile trees, `contracts/provenance/`,
`contracts/realization-envelopes/`, `contracts/concept-authority/history/` —
and `migration/` corpora route alongside `valid/` ones.
`test_every_checked_in_contract_payload_is_routed_or_frozen` holds the
invariant over the whole tree, so a new corpus tree cannot be added unrouted.

Corpus trees are PR-controlled, so discovery applies the repository's
regular-file boundary (`is_regular_repo_file`) before it reads anything. A
tracked symlink is never dereferenced: `Path.is_file()` would follow one, and
both the schema-version read and `check-jsonschema` would then consume
whatever it resolves to on the runner, putting host-resident content into
policy diagnostics. The same boundary applies to declared evidence below.

There is exactly one class of exception, and it is not a waiver. A document
pinned in `tools/policy/historical_identity_records.json` preserves a dated
fact in the shape its contract had when it was written, and
`tools/check_identity_cutover.py` pins it by content hash. It is not a live
document of the contract as published now: validating it against a later
revision would demand an edit that the pin forbids and that would destroy the
record. Those documents are excluded from routing, never from a contract's
coverage — the live document beside them still routes, which is why
`contracts/provenance/sdl-lineage-ledger-v1.json` is excluded while
`sdl-lineage-ledger-v2.json` carries the contract's corpus coverage.

## Repairing a reported gap

`[schema-coverage-missing]` names the schema path that has no evidence. Resolve
it against the contract's own validation and assurance rules, strongest first:

1. **Route an existing payload.** When a real document of the contract already
   sits in the tree unvalidated, add its source tree to
   `_VERSIONED_SCHEMA_ROUTES` in `tools/check_json_artifacts.py`. The document
   is then validated by the contracts lane and coverage follows derivatively.
   This is a row in a table, never a per-contract branch in the coverage gate.
2. **Add a real example document.** Most contract families keep
   `contracts/fixtures/<family>/<contract-id>/{valid,invalid}/*.json`. A
   positive case must satisfy the published schema and its reference model; a
   negative case must be rejected by a named layer — the published schema for a
   shape defect, the reference model for a schema-valid but semantics-invalid
   one. Both layers are legitimate, and a negative case that nothing rejects is
   not evidence.
3. **Declare the alternate evidence.** Where the contract has no standalone
   document at all, record the association on the publication record.

Do not bulk-create placeholder documents to turn the gate green, and do not
waive a finding through `tools/policy/exceptions.yaml` because a repair is
inconvenient. The waiver mechanism exists for a finding that is factually
wrong.

## The `coverage` association

`tools/check_schema_publication.py` does not validate unknown keys on a
publication record, so `tools/check_schema_coverage.py` owns this shape end to
end. In `contracts/schema-publication/entries/<contract-id>.json`:

```json
"coverage": {
  "rationale": "Why no conventional corpus route reaches this contract.",
  "sources": [
    {
      "kind": "embedded",
      "path": "contracts/schemas/experiment-core/experiment-run-v1.json",
      "pointer": "/x-raes-invariants/0",
      "schema_pointer": "#/$defs/RaesSemanticInvariantEntryModel",
      "supports": "The behavior and validation phase this source carries."
    }
  ]
}
```

- The key set is closed at both levels. `rationale` runs 20–500 characters and
  each `supports` 10–200, naming the behavior and the validation phase rather
  than restating the contract id.
- `sources` holds one to eight unique paths. One schema may cite several
  sources, and several schemas may cite one shared source.
- Every path is checked with `safe_repo_path` and `is_regular_repo_file` — so a
  symlinked component, an escaping path, and an irregular file are all rejected
  — before anything is read, and every read is bounded.
- `kind: "fixture"` is a `.json` artifact under `contracts/` whose own
  `schema_version` claims this contract, in either the `name-v1` or `name/v1`
  spelling, **and which the gate then validates against the checked-in
  published schema**. The claim is identity; the validation is the evidence. A
  deliberately invalid corpus case carries the contract id and is therefore
  rejected, as is a carrier that merely embeds a payload of the contract — a
  carrier is not a payload of what it carries.
- `kind: "embedded"` names a node inside a carrier with an RFC 6901 `pointer`,
  for a contract realized as part of another artifact rather than as a
  standalone document. An optional `schema_pointer` of the form
  `#/$defs/<Name>` selects the published definition the node must satisfy; the
  gate resolves it locally against the published schema's own `$defs` and
  validates the node. Several contracts may share one carrier at different
  nodes, and one contract may cite several nodes.
- A contract id appearing in a list of strings, such as a manifest's
  declared-contract inventory, is a mention and not a payload.

Both kinds are computed, never trusted: the gate resolves the artifact and runs
the published schema over it on every run. That is why there is no kind for
"a test that exercises this contract" — a file containing nothing but the
contract's name would satisfy any reference check, so the gate could never
falsify the claim. Evidence the gate cannot falsify is not evidence.

The gate proves that each named source conforms to the published schema; it
does not claim the source is semantically exhaustive. The `rationale`, the
`supports` text, and review of the diff carry that judgement. An association that produces any validation failure is reported as
`[schema-coverage-declaration-invalid]` and provides no coverage at all: a
stale or duplicated reference never passes on the strength of a sibling that
still resolves. The two rule ids are deliberately distinct, so a malformed
association reads differently from an absent one.

## Reporting

```console
$ uv run --project implementations/tooling/python --frozen --no-default-groups \
    python tools/check_schema_coverage.py --report
```

The report groups every published contract by its covering leg and never gates.
It is the quickest way to see which contracts rest on a declaration rather than
on executable corpus evidence.
