# `sdl-yaml/v1` conformance corpus

This reference describes the normative raw YAML corpus.
The [SDL document model](../../../../specs/sdl/document-model.md)
defines the `sdl-yaml/v1` source profile.

- `valid/` documents must pass strict source decoding.
- `invalid/` documents must fail strict source decoding.
- `migration/` documents must fail strict decoding, then pass only when an
  explicit migration policy is selected and must produce at least one
  source-ranged warning.

These files test YAML presentation rules that JSON Schema cannot express.
The separate `contracts/schemas/sdl/sdl-authoring-input-v1.json` schema checks the normalized authoring object.
That object exists after source decoding and typed normalization.

`test_sdl_source_format.py::test_normative_source_profile_fixture_corpus`
checks the three corpus outcomes.
Use the [local check guide](../../../../docs/develop/check-specification-contracts.md#check-fixture-behavior)
to repeat that case.
