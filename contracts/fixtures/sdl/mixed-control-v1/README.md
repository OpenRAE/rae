# Mixed-control SDL fixture corpus

This reference describes portable ACT-617 mixed-control authoring evidence.

- `valid/` documents must pass strict source decoding and semantic validation.
- `invalid/` documents must pass strict source decoding but fail mixed-control
  semantic validation for the boundary named by the fixture.

These fixtures complement the presentation-only `sdl-yaml-v1` corpus, whose
invalid documents fail before semantic validation.

The [mixed-control reference](../../../../specs/formal/participant-semantics/reusable-mixed-control.md)
gives the exact policy and occurrence rules.
`test_act_617_mixed_control.py::test_published_valid_and_invalid_sdl_fixtures_exercise_mixed_control_boundary`
checks this corpus.
Fixture acceptance does not establish native runtime execution.
