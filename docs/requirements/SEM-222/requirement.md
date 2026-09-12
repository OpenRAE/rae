---
id: SEM-222
title: "Participant Episode, Reset, And Termination Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:33.467882Z
updated_at: 2026-08-02T17:17:19.167051Z
---

# SEM-222 — Participant Episode, Reset, And Termination Semantics

## Statement

The ecosystem shall define explicit semantics for participant episode boundaries, initialization, reset behavior, completion, timeout, truncation, interruption, and other termination outcomes.

## Rationale

Primary-source refresh shows that episode lifecycle meaning must be explicit if participant runs, trajectories, and benchmarks are to remain portable and comparable.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-episode-model/README.md` (Participant episode + budget model formal design (issue #122))
- TESTS → TEST `implementations/python/tests/test_sem_222_episode_termination_semantics.py` (SEM-222 episode/termination semantic-gate + closure-record unit tests)
- TESTS → TEST `implementations/python/tests/test_sem_222_episode_termination_oracle.py` (SEM-222 EBM-02/03/08/10 executable invariant oracle)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_episode_closure.py` (SEM-222 RL termination/truncation closure record contract + fail-closed validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_result_contracts.py` (SEM-222 runtime episode-closure validation diagnostics seam (EBM-10 enforcement point))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/result_contracts.py` (SEM-222 public re-export of participant_episode_closure_contract_diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_state.py` (SEM-222 RuntimeSnapshot participant_episode_closure_records carrier (canonical closure-validation wiring))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py` (Published runtime-snapshot-v1 participant episode closure-record carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/snapshot_semantics.py` (Published runtime snapshot closure-record preservation and semantic validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_snapshot_updates.py` (RuntimeSnapshot update-builder module split out to admit the SEM-222 closure-records field under the source-size cap)
