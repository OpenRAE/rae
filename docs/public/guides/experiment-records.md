# Keep complete experiment records

Produce a bundle that accounts for every started run, including runs with missing results.

## Before you start

Use the Python runtime in RAES 11.0.2.
Keep the `RuntimeControlPlane` that admitted your experiment, its `experiment_id`, stores, and installed evidence owners.
The caller needs the original experiment's actor scope.
An experiment ID alone grants no access.
This is a host-composition task; a standalone script cannot supply these owners.

## Collect the bundle

Use `RuntimeControlPlane.experiment_records(experiment_id, ...)` to read every started run.
The method keeps the actor scope that was admitted for the experiment.
It does not start trial effects or permit resource reuse.

Pass `identity=` with the admitted caller identity.
Omit `archive` when you need inspection without an external archive write.
The builder can retain record decisions in its runtime store.
It is not an unlocked read of that store.

A run can exist without a score.
For example, a node can fail to start before a model is called.
Keep that run. State that its score is missing.
Do not turn the missing score into zero.

## Supply observed facts

Pass `metadata` as a map from started run IDs to `ExperimentRunMetadata`.
Installed owners supply apparatus facts, participant provenance, measured results, and disclosures.
Supply `outcome_status` from the scientific evaluation owner.
It defaults to `not-evaluated`.
Execution success and a reported measurement do not establish scientific success.
A completed execution can have a failed or inconclusive scientific outcome.
For complete records, an evaluation can succeed even when execution failed.
The builder does not infer model identity or prompt delivery from a settings digest.
Keep protected prompts and secrets with their authorized owners.

The `evidence_reader` callback opens fresh readers for each complete candidate.
It returns `ExperimentRunEvidenceInputs` for the exact run version.
Its capture specs must match the admitted specs.
Its evidence records must match the stored observations.
The builder does not fetch artifact URIs.
The callback transfers reader ownership to the builder.
The builder closes those readers after checks, including when a timed-out callback later returns.
An evidence-reader failure leaves the record available with failed checks.

## Read the results

The `ExperimentRecordBundle` contains current run records and stored history.
It also contains protected source artifacts, check results, and `ExperimentAccounting`.
`validation_records` identify the exact run versions used by `validation_by_run`.
These can be original scientific versions beside newer accounting versions.
The builder accepts that join only when all scientific facts match exactly.
It resolves the original from either archive path and repeats the evidence checks.
An earlier reader outage does not erase the original artifact.
The new accounting record pins the original through a version and digest in `derived_from_refs`.
Changed measurements need new evidence; the original proof does not move to the accounting version.

Counts distinguish runs from attempts and retries.
Scientific outcome counts remain separate from execution outcome counts.
They show replacements, unresolved work, capture status, cleanup status, and evidence check results.
Each metric states its started, reported, missing, withheld, and eligible run counts.
Missing results receive unused keys; supplied result entries remain intact.
The eligible population uses the same rules as study membership.
Replaced parents remain reported but do not enter the eligible population.
Large evidence histories remain in protected sources with exact versioned references.
A failed cleanup does not erase a measured score.
It also does not make the target safe to reuse.

Protect the returned source data.
It can contain sensitive settings and evidence.
Apply the disclosure rules of your deployment before you share it.

## Build a study record

Pass an authored `study` definition to build exact run-version membership.
The builder pins that definition for resume.
It keeps its claims, target counts, and analysis policy.
It reports failed checks and shortfalls without deleting run history.
Each study snapshot cites its original definition by version and digest.
Authoritative study validators require that exact definition as `study_definition`.
They check that the snapshot preserves its policy and evidence relations.
Evaluation membership names the exact checked version.
Additional accounting versions remain separate members with role `other`.

## Write to a configured archive

Pass an `ExperimentRecordArchive` that is approved for your deployment.
Confirm destination approval before supplying it. Record data can contain protected settings and evidence.
If readback conflicts, preserve the existing version and investigate the difference.
Do not overwrite an immutable record to complete a retry.
The owner stores source artifacts under their own fixed keys.
It writes run and study versions that cannot change.
The runtime freezes each candidate before the write and checks exact readback.
A repeated call resumes stored candidates after a lost reply.
The archive must accept an identical write and reject conflicting bytes.
Each supplied archive receives the records, even after publication to another archive.
This includes the checked scientific versions and retained replacement history.

Partial run versions depend on their stored facts.
Complete records use the owner's `run_version`, which defaults to `1`.
Captured evidence can pin that version before the archive write.
Changed complete content needs a new explicit version.
Version ownership includes records from the existing replacement archive path.
Conflicting content is rejected before any candidate or archive write.
Use a new version to retain additional accounting facts beside an existing archival version.
Old stores without observed end times remain partial.
Reading a record never invents a missing historical time.
The legacy replacement archive also freezes its candidate before writing.
A lost acknowledgement resumes the same bytes and keeps the version reserved during recovery.
## Assigned execution

The [assigned-trial API](assigned-trials.md) retains the original experiment admission across execution hosts.
`ingest_trial_outcome()` verifies remote facts through an explicitly installed original-evidence owner.
Accepted observations feed the same run and study producer described here.
Started assignments without terminal results remain partial or indeterminate records.
Duplicate delivery preserves the original attempt, evidence, and run identity.

## Finish and retain evidence

Success returns an `ExperimentRecordBundle` with run records, accounting, and validation results.
Inspect `validation_by_run` and `validation_failures` before using measurements.
Restore authorized evidence readers and repeat validation when missing evidence becomes available.
Do not replace failed checks with invented measurements.
The builder closes transferred evidence readers. The host owns archive connections and runtime shutdown.
Use the original runtime cleanup path before reusing resources.

Read the {py:class}`RuntimeControlPlane <raes_runtime.RuntimeControlPlane>` for the method signature.
Read [experiment concepts](../concepts.md) for the distinction between execution and evidence.
