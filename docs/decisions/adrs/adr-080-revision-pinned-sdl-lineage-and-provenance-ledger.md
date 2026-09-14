# ADR-080: Revision-Pinned SDL Lineage And Provenance Ledger

## Status

accepted

## Date

2026-07-12

## Classification

Classification: FM1

Required artifacts: an explicit invariant list, closed contract models,
published JSON Schema, exact bidirectional catalog coverage, deterministic
offline integrity checks, and unit/integration tests for failure modes and
distribution-visible notices.

Waivers: live DOI, source-host, and documentation availability checks are a
bounded audit rather than a CI invariant. The committed evidence preserves the
review result without making network availability part of repository truth.

## Context

ACES openly acknowledges that it is not a clean-room language, but narrative
lineage tables did not distinguish conceptual influence, translated code,
example similarity, and compatibility. They also did not pin the OCR revision,
prove coverage of the live language catalogs, or record a resolved notice
disposition. That ambiguity is unacceptable for academic review and downstream
distribution.

## Decision

1. `contracts/provenance/sdl-lineage-ledger-v2.json` is the normative lineage,
   derivation, citation-identity, and notice-disposition record. ADR-019
   registers `contracts/provenance/` as a distinct authority root. The package
   loader, installed corpus, policy gate and current traceability select v2.
   Earlier dated preflights and research records retain their historical v1
   references; they do not select the current normative ledger.
2. Every current top-level authoring field, node runtime family, concept
   family, and reference model has a namespaced subject record whose authority
   coordinate resolves to its existing canonical artifact. Coverage is exact
   and bidirectional; matching counts are insufficient.
3. Claims separate syntax, semantics, artifact/code derivation, and examples.
   `adopted_syntax`, `adopted_semantics`, `adapted`, and `raes_native` classify
   provenance. `current`, `removed`, and `planned` classify disposition.
   Compatibility is a separate directional statement.
4. External sources carry immutable identity. Git sources require a full
   commit and pinned artifact boundary; standards require an edition and
   maintaining body; publications keep title, authors, year, container, DOI,
   and URL as independently checkable fields.
5. Artifact/code claims require a resolved third-party disposition. The OCR
   v0.21.2 derivation is pinned to
   `fe83e8281fc4b954967fbaa5a0d099007ddcb06c`. Because initial ACES history
   explicitly describes translated OCR structures, ACES conservatively ships
   the upstream MIT notice in `THIRD_PARTY_NOTICES.md` and includes that notice
   in source and wheel distributions.
6. `tools/check_sdl_lineage.py` validates the ledger offline using existing
   catalogs and schemas. Live DOI, GitHub, and documentation lookups occur only
   during a bounded audit whose evidence is committed under
   `docs/research/lineage/`; CI never treats network availability as truth.
7. `docs/explain/sdl/precedents.md` and `lineage.md` are explanatory views.
   They may summarize the ledger but may not establish a competing source or
   classification registry. Ambiguous current claims such as "direct port"
   are prohibited.

## Consequences

### Positive

- Reviewers can distinguish influence from copying and compatibility.
- Catalog growth without a provenance record fails deterministically.
- Bibliographic identity mismatches and unresolved derived-code notice status
  fail before release.
- ACES-native additions are visible rather than falsely attributed to an
  older source family.

### Negative

- Language-family additions must update one more normative contract.
- The initial ledger is deliberately conservative about OCR notice inclusion;
  narrowing that disposition requires new evidence and an explicit amendment.

### Limits

The ledger is an evidence-backed engineering record, not legal advice, a
clean-room certification, a proof of behavioral equivalence, or a claim that
all external links remain available forever. It does not change SDL semantics.

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-09-14 | #1210 | Advanced current lineage authority to ledger v2 for the progressive semantic cutover; v1 remains a dated historical record. |
