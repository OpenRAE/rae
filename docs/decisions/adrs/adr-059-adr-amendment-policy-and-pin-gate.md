# ADR-059: ADR Amendment Policy and Acceptance-Content Pin Gate

## Status

accepted

## Date

2026-06-10

## Context

[ADR-000](adr-000-use-adrs.md) and `docs/decisions/adrs/README.md` state that
ADRs are **immutable once accepted** and that the corpus is therefore citable:
a reference to "ADR-048 as accepted" should mean a fixed, knowable piece of
text. That claim was aspirational, not enforced. Git history shows accepted
ADRs edited after acceptance — for example ADR-048 (`e782722` added structured
mapping manifests, `adf63e5` added cardinality fields), ADR-052 (`d727d84`,
`e815f27`), and the same pattern on ADR-025/029/032/038/041/050. Some of those
edits were substantive design changes, not typos. Nothing in the verification
graph noticed, so the citability property the README advertised was silently
false.

Two failure modes follow from an unenforced claim:

- a reader cannot trust that "the accepted ADR" is the text they last read; and
- a genuinely needed correction has no recorded, reviewable form — it either
  masquerades as "still the original" or it is avoided, both of which corrode
  the record.

The fix is not to forbid all change (decisions legitimately evolve) but to make
change **recorded and detectable**: pin each accepted ADR's content, and require
that any substantive change be either a new superseding ADR or an explicit,
in-band amendment record.

## Decision

### 1. What "accepted" pins

An ADR's **canonical content** is its file with the `## Amendments` section
removed, per-line trailing whitespace stripped, and exactly one file-final
newline. Only the file-final newline run is normalized (so a final-newline
toggle is not a change); leading and interior blank lines are significant, so
adding or removing one is a real content change the pin detects. The corpus pins
the `sha256` of the canonical content of every ADR whose status is exactly
`accepted`. Because the `## Amendments` section is excluded, recording an
amendment never perturbs the pin — keeping history honest cannot itself look
like tampering.

Pin scope follows status:

- `accepted` ADRs are pinned and governed by this policy.
- `proposed` ADRs are still being decided and are freely mutable; they are not
  pinned.
- `superseded by ADR-NNN` and `deprecated` ADRs leave the pinned set. The
  citable decision has moved to the superseding/replacing ADR; the old text is
  frozen by virtue of no longer being the live decision, and its manifest pin is
  removed when its status changes.

### 2. The pin manifest

`docs/decisions/adrs/adr-index.yaml` is the machine-readable, **mutable** pin
manifest (the README index table remains the human-facing index, validated
separately by the existing repo-policy ADR-index check). Its shape:

```yaml
hash_algorithm: sha256            # the only supported algorithm today
adrs:
  - id: ADR-048                   # ADR-NNN, unique
    path: docs/decisions/adrs/adr-048-...md   # repo-relative, non-escaping
    pin: <sha256 of canonical content>
    amendments:                   # optional; present for amended ADRs
      - { date: 2026-06-07, ref: e782722, summary: "..." }
```

The algorithm lives in the manifest rather than baked into a rule id or
filename, so a future migration to another digest is a manifest change, not a
code change.

### 3. Amending an accepted ADR

A **substantive** change to an accepted ADR — anything that changes its meaning:
the decision, its scope, normative references, invariants, or the artifacts it
points at — is legitimate only when recorded one of two ways:

1. **Supersession.** Add a new ADR that supersedes it, and set the old ADR's
   status to `superseded by ADR-NNN` (the ADR-005→ADR-006 pattern). The old ADR
   leaves the pinned set; the new ADR is pinned.
2. **In-band amendment.** Keep the ADR `accepted`, append a row to its
   `## Amendments` table, and update its pin in `adr-index.yaml` — **in the same
   change**. A pin bump on its own is not enough: the change must also add the
   amendment record.

An **editorial-only** change — pure formatting, whitespace, or typo fixes that
change no reference and no meaning — is still a change to canonical content, so
it still updates the pin **and** records a `## Amendments` row (a one-line
"editorial: …" summary is enough). The gate is filesystem-only and cannot tell
an editorial fix from a substantive one, so it requires the same in-band record
for both: every canonical-content change to an accepted ADR is recorded, with no
silent-edit escape hatch. The friction of a one-line row is the price of the
citability guarantee — an editorial amendment row is cheap; an unrecorded edit is
the failure this ADR exists to prevent.

The `## Amendments` section is a Markdown table at the end of the ADR:

```markdown
## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-06-07 | e782722 | Added structured datastore mapping manifests. |
```

Each table row corresponds 1:1 (by commit/PR ref) to a manifest `amendments[]`
entry for that ADR.

### 4. Enforcement

`tools/check_adr_immutability.py`, wired into the `policy` nox session, enforces
this filesystem-only and deterministically (it never calls Ground Control, so it
cannot become flaky in CI):

- the manifest is well-formed (`sha256`, unique ids, repo-relative non-escaping
  paths validated by the shared `safe_repo_path`);
- every `accepted` ADR is pinned and every manifest entry names an `accepted`
  ADR (coverage both ways);
- each pin equals its ADR's current canonical hash — the unrecorded-edit
  detector;
- manifest `amendments[]` refs match the `## Amendments` rows 1:1;
- under `--base-rev`/`--staged` (CI runs `--base-rev`), an accepted ADR whose
  canonical content changed versus the base must have gained a `## Amendments`
  record in the same change — closing the "bare pin bump blesses an edit" gap.

## Consequences

**Positive**

- The README's citability claim becomes true and is mechanically defended.
- Legitimate evolution is preserved with a low-friction, reviewable path.
- The manifest gives tooling a stable map from ADR to acceptance-content hash.

**Negative / costs**

- Editing an accepted ADR now requires a manifest pin update plus a
  `## Amendments` row — even for an editorial fix. This is the intended friction;
  it keeps the gate filesystem-only with no silent-edit escape hatch.
- The editorial-vs-substantive line affects only how much you write in the
  amendment summary, not whether you record one; the policy resolves doubt toward
  recording.

**Risks**

- The pin is over normalized canonical bytes; a future change to the
  normalization rule would re-pin the whole corpus. The rule is therefore kept
  minimal (drop the `## Amendments` section; strip per-line trailing whitespace;
  normalize only the file-final newline) and lives in one place shared by the
  manifest generator and the checker.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-11-06 | #1929 | The manifest no longer stores a per-ADR content pin or a hash algorithm. The gate compares each accepted ADR with the base revision and requires an `## Amendments` row for any canonical-content change; git holds the history. |
