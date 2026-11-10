# SDL operation verification for issue 1785

The Go operation owners use frozen Python results and native boundary tests.
This index records the evidence for issue 1785.
It does not replace the hosted checks or claim that they have passed.

The behavior reference is the unchanged Python source tree at
`17bf4515bf12747af69c8598a2fc82d73e9651b9`.
The delivery base is `go-cutover`.
No Python product file, published schema, or published golden expectation changes.
New operation fixtures are separate from the published golden corpus.
Their recorders call the reference owners and support `--check`.
Large reference fixtures use gzip with a fixed zero timestamp.
Compression preserves the exact decoded JSON bytes and keeps each stored file
within the repository size limit.
Snapshot fixtures store a reference SHA-256 digest of the exact snapshot bytes.
The native tests compare both the full document and that digest.

## Acceptance evidence

Paths in this table start at `implementations/go/` unless stated otherwise.

| Issue criterion | Implementation | Verification |
| --- | --- | --- |
| Instantiate, select, compose, transform, and migrate SDL | `internal/sdl/authoring/instantiate.go:45`, `selection.go:26`, `imports.go:80`, `transformation.go:40`, `migration.go:37` | `TestInstantiationReference`: 124 cases, including 43 selections; `TestTransformationReference`: 19 cases; `TestMigrationReference`: 171 cases; `TestOwnedReferenceRewriteReference`: 96 cases |
| Preserve the six command surfaces | `internal/parity/semantic_operations.go`, `module_operations.go`, and `runners.go` | `TestSDLOperationCommands`: 635 frozen command cases; `TestPublicationComparisonKeepsStableIdentity` checks the nonce comparison boundary |
| Verify Python signatures and reject changed modules | `sdl/module/verify.go`, `signature_encoding.go`, and `archive.go` | `TestRegistryVerifiesPythonSignedArtifact`, `TestSignatureBindsPublishedCoordinates`, `TestSignatureEncodingAndUnsignedPolicy`, and `TestSignatureCandidateFailureKeepsValidAlternative` |
| Keep input bounds, integrity checks, errors, and recovery | Source, contract, authoring, and module owners described below | Native boundary tables below; existing source and constructor boundary tests |
| Keep historical defect behavior | Shared admission, reference, provenance, and migration owners | The defect table below names reference tests and native evidence |
| Address the issue's review findings | Ordered binding diagnostics, independent concrete admission, standard Ed25519, bounded inventory, and shared source budgets | `TestInstantiationCollectsBindingErrorsAndRedactsValues`, `TestInstantiationRejectsIntroducedTokensAndForgedFlags`, signature tests, archive tests, and source budget tests |
| Design before implementation | `implementations/architecture.json`, the operation design, and the architecture overview | Ground Control design records and `archcheck -design`; the full architecture check also passes |
| Pass hosted quality checks | Existing CI workflows and Ground Control review and readiness gates | Full suites, race checks, coverage, regression, fuzz, and mutation remain hosted gates |

The publication comparison checks the module slot, digest prefix, nonce grammar,
and matching index path before it removes the independent random nonce.
It compares all other result fields and generated files.
The runner never reads the expected result.

## Input, integrity, and recovery boundaries

| Boundary | Native evidence |
| --- | --- |
| Physical source, aliases, aggregate imports, depth, bytes, and nodes | `internal/sdl/source`: `TestPhysicalSourceBounds`, `TestAggregateDefaultCeilings`, `TestCompositionBudgetBoundaries`, and `TestAllParserLimitDefinitions` |
| Composed model and substitution allocation | `internal/sdl/authoring/buffer_limits_test.go`: repeated strings, nested maps, shared copy budgets, aliases, model JSON, and namespace growth |
| Selection request and optional trial bounds | `TestRecordedSelectionRequiresCompleteValidOutcomes`, `TestSelectionTrialInputBound`, and `TestInstantiationReference` |
| Concrete phase isolation, private names, and copied results | `TestFamilyAdmissionOwnsPhaseAndReadsNoAmbientSources`, `TestInstantiationRejectsIntroducedTokensAndForgedFlags`, `TestConcretePhaseAdmissionPreservesSuppliedFields`, and `TestDecodedDocumentOwnsItsBytes` |
| Transformation request bounds and atomic refusal | `TestTransformationRequestBound` and `TestTransformationReference`; refusal cases return no document or partial linked output |
| Compressed, decoded, member, total, metadata, path-depth, and entry bounds | `TestArchiveInspectionBoundsAndPaths` and `TestArchiveExactLimitsAndGzipPadding`; each exact boundary also has an over-limit case |
| Traversal, links, special files, reserved paths, duplicates, and filtered modes | `TestArchiveInspectionBoundsAndPaths` |
| Complete gzip validation, padding, concatenated members, and corrupt trailers | `TestArchiveGzipSequenceValidation` and `TestArchiveInspectionBoundsAndPaths` |
| Native integrity before optional trust admission | `TestTrustCallbackOnlyNarrowsNativeAdmission`, `TestOCIMetadataRefusesInvalidUTF8`, and `TestRejectedResolutionDoesNotPublishCache` |
| HTTP status, declared and streamed length, cancellation, and redirect authority | `TestHTTPResponseBoundsAndCancellation`, `TestRegistryRedirectCannotChangeAuthority`, and `TestRegistryFetchesOnlyAuthorizedBoundedArtifacts` |
| Exact locked manifest and callback request facts | `TestLockedResolutionUsesExactManifestAndRequestFacts` and `TestLockDecoderAndLocalResolution` |
| Copied verified sources, lexical confinement, missing members, and aggregate imports | `TestVerifiedSourceSnapshotIsConfinedAndOwned`, `TestVerifiedSourceSnapshotKeepsImportBudget`, and `TestCompositionUsesVerifiedRegistrySources` |
| Linked cache roots, stores, lock parents, and lock files | `TestRegistryRejectsLinkedCacheRoot` and `TestCacheRejectsLinkedStoresAndLocks` |
| Cache content, modes, extra or missing files, metadata, and special files | `TestCacheRebuildsEveryInventoryMutation` and `TestCacheRepairsCorruptionAndRecoversOrphans` |
| Concurrent writers and canceled lock acquisition | `TestCacheConcurrentWritersReuseOneVersion`, `TestCanceledLockDoesNotCreateOrAcquireFile`, and `TestLockWaitHonorsCancellationAndRejectsFIFO` |
| Orphan recovery, prior readers, bounded retention, and pointer ordering | `TestRecoverySkipsUnrelatedVersionDirectories`, `TestPublicationRetainsCurrentPriorAndNewestVersions`, and `TestVersionPruneFailurePreservesPointer` |
| Deterministic publication and usable immutable results | `TestPublicationIsDeterministicSignedAndRecoverable`, `TestPublishedBundleMatchesPythonByteProfile`, and `TestPublisherPathAndWindowByteProfiles` |
| Stable source-tree identity for reference recorders | `implementations/python/tests/test_issue_1785_reference_history.py`; changed history is accepted only when the pinned source tree is unchanged |

The publisher and cache share `installVersion`, staging, synchronization,
retention, and atomic pointer replacement.
Pruning completes before the current pointer advances.
Regular-file reads use rooted descriptors, identity checks, and no-follow opens.
Verified module sources come from authenticated archive bytes.
The parser does not reopen the cache to obtain those sources.

## Review corrections

The first review found three operation defects.
Each repair has a targeted regression test.

| Finding | Repair | Verification |
| --- | --- | --- |
| Publication can retain an import that needs an omitted workspace lock | Refuse non-local source declarations before lock alias resolution, including nested modules | `TestPublicationRejectsLockDependentGraph` checks that the workspace graph composes, then checks atomic publication refusal |
| Declaration changes retain old provenance paths | Share path reconciliation with selection; rename model paths and field pointers, or remove records for a removed declaration | `TestTransformationKeepsImportedProvenance` transforms, instantiates, and checks explicitness, capability constraints, parameter derivations, realization constraints, and realization designations |
| OCI lock resolution accepts unknown parameter names | Retain the verified descriptor's parameter names and apply the local resolver's parameter check before returning a lock record | `TestOCILockRejectsUndeclaredParameters` and `TestOCILockAcceptsDeclaredParameters` cover refused and admitted requests |

The frozen Python composed-rename result retains five old explicitness paths.
Its fixture bytes remain unchanged.
The Go reference test corrects those five exact expected path strings before the
full output comparison.
It compares the report and every other reference field unchanged.
The separate transformation and instantiation regression checks the corrected
provenance behavior.

## Coverage evidence

`parity_module_policy_vectors.py` records 103 trust-policy inputs and 783 version
requests and results from the pinned Python owner.
It supports `--check`; a Python test also checks the frozen results.
`TestWorkspacePolicyReference` and `TestVersionRequestReference` compare native
admission and complete policy values with those results.
The cases include YAML aliases and merges, scalar types, closed keys, registry
flags, signer maps, and version ordering and constraints.

`TestSharedReferenceRulesOnConstructedDocuments` checks that shared temporal,
stateful-resource, and service-content findings agree with the frozen Python
messages and owners for constructed documents.
Additional tests check lockfile fields, optional and absent locks, explicit
workspace authority, atomic publication refusals, and version-tag selection.
Targeted coverage profiles extend the hosted report.
The hosted coverage gate remains authoritative.

## Defect evidence and design differences

The Python test names below identify behavior, rather than a Python class layout.
Shared source and semantic checks remain with the owners delivered before this issue.

| Reference tests or defect family | Native evidence or scope boundary |
| --- | --- |
| `test_sdl_phase_contracts.py`, `test_instantiated_scenario_schema.py`, and `test_scenario_family_admission.py` | Instantiation vectors, independent phase admission, family isolation, copied bytes, and forged-phase tests |
| `test_issue_1481_parameter_authority.py` | Forty-three `issue-1481-*` vectors cover configurable leaves, required and default values, finite controls, interpolation, nested imports, correlated parameters, classified alternatives, and tampered derivations |
| `test_issue_1625_structural_variation.py`, `test_issue_1733_dependent_declaration_variation.py`, and `test_sce_002_selected_scenario.py` | Recorded selection vectors cover all outcome kinds, conflicting writes, node and inventory changes, dependent declarations, and retained evidence |
| `test_issue_1747_rule_source_variation.py` | Twenty-five `issue-1747-*` vectors cover owner and candidate eligibility, generator resolution, source order, dependent removal, conflicting and equal writes, imported identities, and retained provenance |
| `test_issue_1107_oci_source_snapshot.py` | Verified snapshot tests, immutable copied bundle sources, cache repair tables, and composed Python-signed nested graphs |
| `test_issue_1339_import_safety.py`, `test_issue_1339_editor_imports.py`, and `test_issue_1757_supplied_sources.py` | Existing `TestImportReference` and source containment tests retain pins, lock chains, budgets, local trust, and supplied-source refusal before registry dispatch |
| `test_issue_1339_reference_eligibility.py` and `test_issue_1339_scope_and_effect_integrity.py` | The existing native declaration index and semantic admission remain authoritative; owned-reference vectors cover rewrite surfaces while prose and opaque values remain data |
| `test_issue_1208_profile_composition.py`, `test_issue_1361_policy_composition.py`, and `test_issue_1361_execution_policy.py` | Shared reference and policy owners; import policy tests; transformation policy vectors; `TestRegressionPolicyRewriteKeepsRootScope` |
| `test_issue_1210_semantic_migration.py`, `test_issue_1338_identity_migration.py`, `test_issue_1363_mixed_control_migration.py`, and `test_classification_migration.py` | Migration vectors cover all four profiles, source-bound decisions, conflict and loss refusals, linked bindings, snapshots, exact reports, and atomic output |
| `test_issue_1678_sdl_input_refusals.py`, `test_issue_1678_sweep_s.py`, and mixed-control finding tests | Sixty-four migration source-boundary vectors and four typed transition-location vectors; native regression tests cover exact transition pointers |
| Python mutation of admitted Pydantic models or private validation flags | Go documents expose copied bytes and private state. Callers cannot mutate fields, omitted defaults, or validation flags. Fresh serialized values must pass native construction and admission |
| Python monkeypatches of `fdopen`, extraction, or platform-specific lock backends | Go uses `os.Root`, standard descriptors, and Linux kernel locks. There is no `fdopen`, extraction callback, fallback extractor, or Windows lock backend in this target. Native tests exercise actual filesystem failures, special files, cancellation, corruption, and concurrent writers |
| Backend generation and execution tests that call instantiation as setup | Backend actions, planning, realization relations, runtime execution, and language-service completion belong to their own owners. This change supplies admitted SDL results; it grants none of those authorities |

`random_value.py` owns a value-free recipe and admission rules.
The native contract owner already enforces those rules.
This issue does not add a random-value backend.
The finite derivation image and its realization-relation budget belong to the
consumer that evaluates that relation; SDL carries the checked derivation records.

Regression tests use APIs that exist at the delivery base.
They cover the sibling enum default, typed mixed-control location, and root policy scope.
CI proves the baseline failures and the fixed-head successes.
No full regression or mutation lane runs locally.
