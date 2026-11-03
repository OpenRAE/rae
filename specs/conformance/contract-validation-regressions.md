# Contract validation regression crosswalk

This crosswalk covers issue #1780.
The published schemas remain the authority.
The [rule inventory](contract-invariant-rules.json) specifies all annotated rules.
The [source crosswalk](contract-predicate-sources.json) names their Go predicates and reference owners.

## Validation claims

| Claim | Go check | Reference evidence |
| --- | --- | --- |
| Published schema acceptance | `parity.TestCorpus/schema validate` | Recorded schema verdict for every routed fixture |
| Portable contract admission | `parity.TestPortableContractAdmissionCorpus` | 363 recorded CLI contract-admission cases, including input and unknown-contract refusals |
| Full admission with recorded owners | `admission.TestFullValidationGoldenCorpus` | 702 inputs from the complete fixture inventory and the original selector regression; separately captured Python model and contextual results |
| Full admission without an owner | `parity.TestFullAdmissionCorpusBoundary` | Same fixture inventory; local claims cannot supply independent context |
| Full admission with an owner | Tests in the next table | Separate source records and reference-admitted owner fixtures |
| Reduced timing-limit fractions | `admission.TestTimingLimitReducedRatiosMatchPython` | 18 Python verdicts through realized time and experiment-run validation, including 2/4 refusal and 1/2 admission |
| Clock coordinate defaults | `admission.TestRuntimeClockPythonDefaults` | 98 Python model verdicts through standalone time state and runtime snapshot admission; exact evidence preservation |

The portable command checks local rules and selected context gates.
Its positive result cannot grant a stronger contextual claim.
The full corpus boundary checks local results and refuses missing external owners.
Tests with trusted records check the accepted contextual paths and changed owner facts.
Each failure returns no admitted `Value`.

## Trusted records

All tests below use the complete production constructor.
They enter through `Validator.Validate` with separate owner records.
A payload cannot create those records.

| Rule family | Go test |
| --- | --- |
| Task and run protocol; study membership, allocation and analysis | `TestTaskRunAndStudyJoins` |
| Apparatus manifests and compatibility | `TestApparatusManifestPayloadJoins` |
| Cleanup plans, receipts and failed cleanup | `TestCleanupReceiptTrustedJoin` |
| Completeness taxonomy and behavioral claims | `TestBehavioralCatalogAndCompletenessFixture`, `TestBehavioralRevisionedClaims` |
| Backend requests, responses and installed capability | `TestBackendOperationTrustedJoins` |
| Artifact parent identity, exact bytes and reader failures | `TestAssociatedArtifactsBindDeclaredBytes`, `TestPublishedAssociatedFixturesAgainstReferenceOwners` |
| Information sources, history and exact state cut | `TestInformationStateStrongClaimResolvesExactCut` |
| Control agreement, installed bindings and incumbent gates | `TestControlContextTrustedSelectionAndLifecycle`, `TestControlResolvedContextBindsIndependentOwners` |
| Control occurrences and declarations | `TestControlOccurrenceJoinsCompiledDeclarationAndTransformedSource` |
| Crossing decision, attempt and delivery owner | `TestCrossingDeliveryRequiresItsExactDecisionAttemptAndOwner` |
| Inject retry, outcome and produced-result correlation | `TestInjectExactRetryAndClaimSet`, `TestInjectOutcomeAndCorrelationSources` |
| Flow authorities, action admission, sinks and history | `TestFlowResolvedContextRequiresExactIncumbentOwners`, `TestOwnerFlowRequiresEachObligationAuthorityAndExactReader` |
| Mixed composition, installed bindings and backend willingness | `TestMixedCompositionResolvesIndependentAuthorityAndTime`, `TestMixedBackendBindingsRequireExactProfileAndWillingness` |
| SDL archive bytes and semantic identity | `TestMaterializationArchiveBindsProtectedBytesAndSemanticIdentity` |
| SDL execution plan, origins, inventory and node scope | `TestMaterializationExecutionBindsIndependentPlanOriginsAndInventory`, `TestMaterializationExecutionRefusesChangedScopeOriginsAndReplicaGaps` |
| Descendant archive lineage, authority and lifecycle | `TestMaterializationInventoryBindsLineageAndLifecycleToProtectedPredecessor`, `TestMaterializationInventoryRefusesIndependentAuthorityAndLineageDefects` |

## Shared limits, errors and recovery

Paths in the reference column are relative to `implementations/python/`.
Go names below are test functions in the contract packages unless a package is stated.
Tests name the specific failure or boundary in their subcases.

| Reference behavior or defect | Go evidence |
| --- | --- |
| `contracts/bundle.py`: cache assembly and return isolated copies | `TestImmutableAdmission`, `TestDefaultsPreserveSchemaAcceptanceAndOwnership`; compiled schemas have no mutable public view |
| `contracts/bundle_runtime.py`: closed roots, array event streams and invariant locations | `TestPublishedSchemaBoundary`, `TestArrayRootAndBindingErrors`, `TestDispatchAcrossApplicators`, schema corpus |
| `contracts/schema_invariants.py`: annotation shape, input contracts and paths | `TestLoadRejectsBrokenResources`, `TestRejectsUnknownInvariantReferences`, `TestRuleSpecificationsKeepLocations` |
| `contracts/schema_constraints.py`: selectors and phase omission constraints | `TestPublishedSecurityRegressions`: 680 independently checked Python schema/model verdicts |
| `contracts/schema_factoring.py`; `test_issue_1241_schema_publication_size.py`: preserve references, instance data and definition names | Schema corpus and `TestInstanceChecksUseOriginalApplicableSchemas`; Go consumes the exact published factored bytes and does not run schema factoring |
| `contracts/validators.py`: known families, contracts and reference bindings | `TestReferenceModelPublishedBindingVerdicts`, `TestReferenceModelDuplicateBindingsAndKeyFields`, `TestReferenceBindingPublishedPathsAndKeyFields` |
| `contracts/validators.py`: nullable wrappers, local pointers, wildcard paths and key declarations | `TestReferenceBindingPublishedPathsAndKeyFields`, `TestReferenceLookupRefusesCyclesAndWorkExhaustion` |
| `contracts/validators.py`: adopted/adapted concept coverage and canonical UCO names | `TestUCOCatalogReferenceVerdicts`, `TestConceptFamilyKeysRequireNonblankIdentity` |
| `corpus.py`; `test_corpus_resources.py`, `test_corpus_packaging.py`: packaged resources without checkout lookup | `corpus.TestPackagedCorpus`; embedded read-only ZIP and installed-binary CI check |
| Missing, corrupt, duplicate or unsafe corpus members | `corpus.TestRejectsCorruptArchives`, `TestLoadRejectsBrokenResources` |
| No file or network lookup through schema references | `TestLoadRejectsBrokenResources` tests external file and HTTP references against an offline compiler |
| Malformed data, invalid root, duplicate keys, non-finite numbers, invalid UTF-8 and trailing documents | `TestFullAdmissionInputFailuresLeaveNoValueAndRecover`, `TestInputLimitsAndExactNumbers` |
| Caller byte and depth budgets, including the inclusive byte bound | `TestFullAdmissionInputFailuresLeaveNoValueAndRecover`, `TestDefaultedObjectFragmentPreservesInputAndBounds` |
| Exact numbers and explicit maintainer decision on Python type conversion | `TestPublishedTypesEnforceMaintainerDecision`, `TestAdmissionExactNumberBoundary` |
| Absent, null, zero and unknown union members | `binding.TestFieldStates`, `binding.TestFieldAccess`, `binding.TestGeneratedRegistry` |
| Raw root JSON methods and large number text | `binding.TestRawRootTransportsPreserveJSONMethods` |
| Missing rule, duplicate rule or typed nil context | `TestCompleteRegistry`, `TestRuleRegistrationAndPrivacy`, `TestTypedNilContextFailsBeforeCallingRule` |
| No successful value after schema, rule, model or owner failure; reuse after refusal | `TestFullAdmissionInputFailuresLeaveNoValueAndRecover`, `TestFullAdmissionRequiresIndependentContextAndRecovers` |
| Private payload and owner errors remain private | `TestRuleRegistrationAndPrivacy`, `TestCatalogIngressFailsClosed`, full-admission failure tests |
| `tools/generate_contract_schemas.py`, `tools/check_generated_schemas.py`: exact published authority | `contractgen.TestGenerateAndDrift`, `TestGeneratorRejectsAuthorityAndPathErrors`, CI `contractgen -check`; Python authority generation stays unchanged |
| Missing specification, missing output and unexpected output | `contractgen.TestMissingRuleSpecification`, `TestGeneratedNestedTypesAndCompleteOutput` |
| `test_issue_1363_schema_parity.py`: every mixed-control declaration, delivery exclusivity and v2 carrier vector | `TestPublishedIdentityAndMixedControlDefects`: all source matrices, across all five published phase schemas and the v2 root |
| `test_issue_1206_vocabulary_schema.py`: every identity field, closed runtime operation and malformed private engine | `TestPublishedIdentityAndMixedControlDefects`: exact published pointers and independent Python model/schema results; 765 vectors across both source files |
| `test_issue_1241_schema_omissions.py`: redacted commands, values and absent filesystem facts | `TestPublishedSecurityRegressions`, across every affected published phase definition |
| `test_issue_301_selector_schema_parity.py`: empty, blank and duplicate selectors | `TestPublishedSecurityRegressions`, across all five affected schemas |
| `test_issue_1778_parity_corpus.py`: fixture identity, provenance and input integrity | Existing parity manifest, runner and case inventory tests; contract fixture tests retain the exact inventory |
| `test_issue_1779_corpus_secret_scan.py`: retain corpus policy checks | Existing corpus policy stays in force; `test_generated_concept_transport_keeps_authority_data_paths_guarded` checks the exact derived Go DTO allowance; `test_generated_transport_does_not_allow_sibling_authority_paths` exercises the real Rego refusals |
| `test_controlled_vocabularies.py`: scope membership, unique ownership and extension policy | `TestControlledVocabularyPublishedVerdicts`, `TestControlledVocabularyModelVerdicts` |
| Backend and processor manifest model validators | `TestManifestCapabilityModelReferenceVerdicts`: 70 recorded model verdicts for capabilities, autonomy, tools and declared contracts |
| Resource policy, quantity, pool, state and event model validators | `TestResourceBudgetModelReferenceVerdicts`: 28 recorded model verdicts for identities, limits, ownership and parent graphs |
| Sealed domain-profile metadata and provenance | `TestDomainProfileModelReferenceVerdicts`: 30 recorded model verdicts for digests, inert identities, sorted declarations and limits |
| `test_issue_1208_resource_profiles.py`: native and private pool admission | `TestResourceProfileReferenceVerdicts`: 45 full-manifest verdicts, including independent positive fixtures and exact resolution, support, schema and budget refusals |
| `test_issue_1202_domain_profiles.py`: safe schema subset and shared evaluation budget | `validation.TestInertProfileReferenceVerdicts`: 33 recorded schema/value verdicts, with the exact minimum accepted evaluation budget for each positive case |
| Private-profile input bounds, malformed JSON, unsupported declarations and recovery | `validation.TestInertProfileLimitsPrivacyAndRecovery`, `validation.TestInertProfileRejectsMalformedInput` |
| Python `re.compile` syntax in vocabulary metadata | `TestMetadataPatternSyntaxMatchesPython`, `TestMetadataPatternLiteralSyntaxRegressions`: 477 recorded compile verdicts, with no pattern execution |
| `test_participant_implementation_manifest.py`: compatibility, exposure policy, participant uniqueness and governed terms | Portable and full fixture corpus checks for participant manifests and provenance |

The source snapshots for metadata syntax tests carry their source hash and license.
Unicode identifier and name-alias data are pinned to the Python reference's Unicode 16 version.
The parser uses finite nesting and width arithmetic.
It does not execute expressions or retain caller expressions.

## Structural and full reference results

The saved CLI corpus records structural validation.
A positive structural result cannot prove a separately supplied parent or execution.
`TestPublishedAssociatedFixturesAgainstReferenceOwners` records seven full Python results
against concrete reference parents and payload bytes.
The scenario passes; the snapshot with a placeholder parent digest fails.
The five experiment attachments also fail against independently supplied parents with different identities.
These full results do not replace or change the original structural golden results.
The maintainer selected separate full results for issue #1780.
`TestFullValidationGoldenCorpus` scans every packaged JSON fixture and the published registry.
It identifies 701 contract fixtures by an enclosing contract ID or a unique schema version.
It also classifies all 14 workflow fixtures and retains the original unknown-selector case.
The smaller 363-case CLI list cannot hide an omitted fixture.
Each of the 702 rows has a separately captured Python model or contextual result.
The actual types used to construct the schema bundle supply model validation.
The published-schema gate runs first to retain the approved type decision.
There are 172 contextual comparisons across 22 families and 80 different full results.
Every contextual row names its independent owner and Python check.
Other contextual families retain separate trusted-owner success and refusal tests.
Original CLI and schema results remain unchanged and are checked against their exact source records.
Every row has a separate Python Draft 2020-12 schema result, including CLI-recorded fixtures.
Go schema checks compare that result independently of full admission and the saved CLI result.
Sixty-nine schema results differ from the saved surface result because the CLI also checked local rules.
The original surface results remain unchanged.
Owner input hashes prevent helpers from silently changing a result's authority.
CI runs the complete table; local checks select affected family rows.
The [verification note](../../docs/decisions/issue-1780-contract-validation-verification.md)
links the pre-implementation design records and states the required check order.

The contextual table exposed inherited empty collection factories in control and crossing records.
`TestEventFactoryDefaultsKeepSuppliedEvidence` checks that comparison defaults retain supplied evidence.
Full reference positives also check that model comparison does not change admitted bytes.

## Verification boundary

Local runs select changed tests and fixture families.
They do not replace complete hosted tests.
CI runs the complete fixture corpus, generator drift checks, coverage, mutation tests and fuzzing.
Design, policy, architecture, review, hosted checks and readiness remain required gates.
A passing local check is not a claim that CI or the review has passed.

## Reference scope and retained checks

The nine shared reference files have the following boundary ownership.
The table separates generation from runtime validation.
Family admission adds the trusted records and model checks listed above.

| Python source | Go boundary and evidence |
| --- | --- |
| `contracts/bundle.py` | Published bytes are the source; `contractgen.TestGenerateAndDrift` rejects changed authority, while `TestImmutableAdmission` prevents shared mutable results. |
| `contracts/bundle_runtime.py` | Root and event-stream bindings follow all 148 entries; `binding.TestGeneratedRegistry` and `TestArrayRootAndBindingErrors` cover both forms. |
| `contracts/schema_constraints.py` | Exact published constraints execute in the maintained engine. The 680 omission and selector vectors and 765 identity and mixed-control vectors retain source defects. |
| `contracts/schema_factoring.py` | Go does not factor or regenerate the normative schemas. It embeds their exact bytes. `TestInstanceChecksUseOriginalApplicableSchemas` preserves compiled branch identity. The unchanged Python drift gate continues to check its own factoring algorithm. |
| `contracts/schema_invariants.py` | `TestRuleSpecificationsKeepLocations` retains input paths and all annotations. `TestCompleteRegistry` binds every published key. Invalid declarations and unknown contracts fail in `TestLoadRejectsBrokenResources` and `TestRejectsUnknownInvariantReferences`. |
| `contracts/validators.py` | Reference binding, nullable wrappers, wildcard paths, concept scopes, uniqueness and UCO coverage have named Go cases in the shared table. |
| `corpus.py` | `corpus.TestPackagedCorpus` reads every resource without checkout lookup. Corrupt ZIP members fail in `TestRejectsCorruptArchives`. The installed-binary CI check runs from an empty directory. |
| `tools/generate_contract_schemas.py` | The Python authority generator stays unchanged. Go `contractgen.Generate` consumes its publication entries and schemas; it cannot become a competing schema authority. |
| `tools/check_generated_schemas.py` | Existing Python drift and schema-coverage gates remain required. Go `contractgen.Check` additionally detects missing, stale and extra derived outputs. |

Python wheel construction, import aliases and package entry points have no Go runtime equivalent.
The Go corpus check tests their relevant outcome: all normative resources work after installation.
Python schema factoring remains an authority-generation operation.
The Go port preserves its output instead of adding a second factoring implementation.
Schema-coverage tooling remains the existing Python policy tool; this issue adds no alternate router.
The Go fixture tests independently scan the packaged contract inventory.

The canonical workflow retains strict lint, repository analyzers, architecture,
race tests, a 90 percent coverage floor, changed-line mutation checks and fuzz smoke tests.
The evidence note links the dated design checks that preceded implementation.
Passing hosted results can only be recorded after publication.
They are prerequisites for readiness and merge, not a claim made by this crosswalk.
