# Published-contract requirement tracing

Every schema under `contracts/schemas/` is a normative published contract
(`ADR-009` §7). `tools/check_schema_publication.py` proves the inventory and
`tools/check_schema_coverage.py` proves that something exercises each contract.
Neither names the requirement that governs a contract, so a schema could be
published with no owner. `experiment-authoring-input-v1` was linked to `EXP-736`
only after review (issue #675, PR #711).

`tools/check_contract_requirement_tracing.py` closes that gap. It runs as the
`policy / published contract requirement tracing` stage of `nox -s policy` and
reads the whole published inventory on every run, not the changed-file set.

## The rule

A published contract is **traced** when at least one requirement record under
`docs/requirements/<UID>/requirement.md` whose status is `ACTIVE` or `DRAFT`
carries this link to the contract's exact schema path:

```markdown
- IMPLEMENTS → SPEC `contracts/schemas/<family>/<contract-id>.json` (<contract-id> published schema)
```

- **Only `IMPLEMENTS → SPEC` counts.** `CONSTRAINS`, `DOCUMENTS`, `TESTS`, and
  `VERIFIES` links record a relation other than ownership. An `IMPLEMENTS` link
  to a schema path typed as `CONFIG`, `SCHEMA`, or `DOCUMENTATION` does not
  count as ownership either. Retype it to `SPEC` only where it records that the
  requirement owns the contract. Some such links record a narrower relation,
  such as the vocabulary or temporal rules one requirement adds to a shared SDL
  schema; leave those as they are.
- **`CODE_FILE` links never count.** A module link cannot say which contract a
  requirement governs. `raes_contracts/contracts/bundle.py` generates every
  published contract and several requirements link it as a `CODE_FILE`, so
  accepting module links would mark every contract traced.
- **The path must match exactly.** A link to a document beside the schema,
  such as the catalog `contracts/concept-authority/behavioral-relations-v1.json`,
  does not trace `contracts/schemas/concept-authority/behavioral-relations-v1.json`.
- **`DRAFT` owners qualify.** Requirement governance admits a `DRAFT`
  requirement for implementation work, and the owning requirements of several
  contract families, such as the time and participant-budget contracts, are
  still `DRAFT`. Requiring an `ACTIVE` owner would force a link to a less
  precise requirement.
- **`DEPRECATED` and `ARCHIVED` owners never count.** These are the statuses
  `tools/policy/requirement_governance.py` rejects for implementation work. A
  contract whose only owner is retired is untraced until a live requirement
  owns it.
- **One live owner is enough.** A contract may have several.

The gate reads requirement records offline through
`RepositoryRequirementClient`, the parser behind the repository requirement
source that `tools/policy/requirement_order.yaml` selects. It makes no Ground
Control request, so it runs on every CI policy run. A record that the parser
rejects, including a malformed traceability line, a symlinked record, or a
directory that is not a canonical requirement UID, fails closed as
`[contract-requirement-record-unreadable]` and owns nothing.

## The inventory

The denominator is every `contracts/schemas/**/*.json` file. The contracts lane
already fails when that tree disagrees with `schema_bundle()`
(`tools/check_generated_schemas.py`) or with the publication manifest
(`tools/check_schema_publication.py`), so the gate reads the tree rather than
regenerating the bundle. `test_issue_712_contract_requirement_tracing.py` pins
the three inventories to one set. A removed schema leaves the tree, so its
tombstone needs no owner.

## Repairing a finding

`[contract-requirement-trace-missing]` names the schema path that has no live
owner. Add the `IMPLEMENTS → SPEC` line to the Traceability section of the
requirement that governs the contract, in the same pull request that publishes
a new schema. Choose the owner by evidence, strongest first:

1. A live requirement already records the exact schema path under another link
   or artifact type, or links the contract's own catalog or publication record.
2. The pull request or commit that published the schema, or its issue,
   declared the requirement.
3. The requirement's statement names the contract's subject. Prefer a
   requirement that also links the contract's defining module, tests, or
   governing ADR.

On a branch that requirement governance checks, the edited record is a changed
file like any other. Where `tools/policy/requirement_order.yaml` maps ownership
roots to the phase of a requirement governing the branch, including one a scope
file binds the record to, the record must fall inside them. Otherwise
governance reports `requirement-ownership-mismatch`. Some phases, such as
`runtime-core`, own schema paths but not their own requirement records.

Do not link a requirement only to turn the gate green. Do not waive a finding
through `tools/policy/exceptions.yaml` because a repair is inconvenient. The
waiver mechanism exists for a finding that is factually wrong.

## Reporting

```console
$ uv run --project implementations/python --frozen \
    python tools/check_contract_requirement_tracing.py --report
```

The report lists every published contract with its live owners, marks a
contract without one as `UNTRACED`, and never gates.
