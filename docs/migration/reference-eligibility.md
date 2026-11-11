# Migrating to purpose-specific reference eligibility

## Before you start

Source: SDL references accepted by the pre-1339 exclusion-based `targetable` rule.
Target: purpose-specific eligibility in RAES 11.0.2.
Retain the original SDL and identify the intended declaration for each refused reference.
Only the author can resolve an ambiguous intended subject.
There is no compatibility reader or automatic converter.
This task edits a local source file and invokes no backend.

## Rewrite and validate

1. Run `raes semantic validate scenario.sdl.yaml` on a copy of your source.
2. Replace each refused reference with the intended eligible declaration from the field table below.
3. Use a qualified address when a bare name is ambiguous.
4. Repeat validation until it exits `0` and prints `validate: success`.
5. Retain the corrected artifact under a new content identity and update its dependent pins explicitly.

Replace `scenario.sdl.yaml` with your source path.
Exit `1` retains diagnostics; it does not authorize a guessed replacement.
For imports, use [file validation from Python](../public/guides/python.md).
No native cleanup is needed. Preserve historical evidence under its original reader and identity.
The dated inventory below remains evidence of its stated revisions only.
Read [reference purposes](../../specs/sdl/references.md#7-reference-purposes-and-eligibility)
and the [SDL explanation](../public/concepts.md) after completing the edit.

## Fields that narrow

Use the [field conversion table](../explain/reference/reference-eligibility-migration.md#fields-that-narrow) to select the intended declaration.

## Typed relationship endpoints

Read [typed endpoint requirements](../explain/reference/reference-eligibility-migration.md#typed-relationship-endpoints).

## Inventory before narrowing

Read the [dated inventory](../explain/reference/reference-eligibility-migration.md#inventory-before-narrowing). Its counts describe those source revisions only.

## Editor behavior

Read the [editor reference](../explain/reference/reference-eligibility-migration.md#editor-behavior) for completion, navigation, and ambiguity rules.

## Unchanged

Read [unchanged fields and boundaries](../explain/reference/reference-eligibility-migration.md#unchanged).
