package authoring

const (
	valueField         = "value"
	importsField       = "imports"
	allowedValuesField = "allowed_values"
	countField         = "count"
	fieldPointerField  = "field_pointer"
	kindField          = "kind"

	noneTerm                    = "none"
	selfTerm                    = "self"
	handoffTerm                 = "handoff"
	evidenceRequirementsSection = "evidence_requirements"
	strictNumberShape           = "number!"
	sharedLayoutKey             = "$shared"
	parameterRefusedCode        = "parameter-refused"
	budgetExceededCode          = "budget-exceeded"
	pathInvalidCode             = "path-invalid"
	localImportPrefix           = "local:"
	sha256Prefix                = "sha256:"
	lockInvalidCode             = "lock-invalid"
	deploymentTenantPrefix      = "deployment_tenants."
	nodesPrefix                 = "nodes."
)

const (
	authoringContract    = "sdl-authoring-input-v1"
	materializedContract = "materialized-scenario-v1"
	dataScope            = "data"
	scriptModelName      = "Script"
	privateSegment       = "__private"
	agentsSection        = "agents"
	architectureField    = "architecture"
	behaviorSection      = "behavior_specifications"
	booleanType          = "boolean"
	conditionsSection    = "conditions"
	exactTerm            = "exact"
	forwardingSection    = "forwarding_agents"
	integerType          = "integer"
	nodesSection         = "nodes"
	numberType           = "number"
	stringType           = "string"
	architectureX86      = "x86_64"
	arbitraryEquality    = "==="
)

const (
	sourceField     = "source"
	featuresSection = "features"
)

const injectsSection = "injects"

const (
	namespaceField     = "namespace"
	contentDigestField = "content_digest"
)

const (
	controlAssetsSection = "control_context_assets"
	exportHashField      = "export_hash"
	nameField            = "name"
)

const moduleIDField = "module_id"

const (
	moduleVersionField    = "module_version"
	resolvedSourceField   = "resolved_source"
	requestedVersionField = "requested_version"
	signerIDField         = "signer_id"
	manifestDigestField   = "manifest_digest"
)

const (
	nullType       = "null"
	mappingSyntax  = "mapping"
	scalarSyntax   = "scalar"
	sequenceSyntax = "sequence"
)

const (
	accountsSection   = "accounts"
	assertionsSection = "assertions"
	workflowsSection  = "workflows"
	servicesField     = "services"
	settingIDField    = "setting_id"
	scopesField       = "scopes"
	eventsSection     = "events"
	boundariesSection = "observation_boundaries"
)

const (
	infrastructureField              = "infrastructure"
	propositionsField                = "propositions"
	entitiesField                    = "entities"
	scriptsField                     = "scripts"
	storiesField                     = "stories"
	contentField                     = "content"
	generatedArtifactsField          = "generated_artifacts"
	persistentVolumesField           = "persistent_volumes"
	identityDomainsField             = "identity_domains"
	relationshipsField               = "relationships"
	variationPointsField             = "variation_points"
	toolAffordancesField             = "tool_affordances"
	participantInjectDeliveriesField = "participant_inject_deliveries"
	controlContextField              = "control_context"
	declarationRefField              = "declaration_ref"
	settingsField                    = "settings"
	mappingIDField                   = "mapping_id"
	templateIDField                  = "template_id"
	scopeField                       = "scope"
	policyField                      = "policy"
	variablesSection                 = "variables"
)

const computeType = "compute"

const (
	runtimeField = "runtime"
	openTerm     = "open"
	falseTerm    = "false"
	trueTerm     = "true"
	otherTerm    = "other"
)

const accessObservationsField = "access_observations"

const unknownTerm = "unknown"

const tcpProtocol = "tcp"

const (
	identityForestsField   = "identity_forests"
	identityFacadesField   = "identity_facades"
	deploymentTenantsField = "deployment_tenants"
	databaseServicesField  = "database_services"
	participantField       = "participant"
	databaseAccessField    = "database_access"
	mailAccessField        = "mail_access"
)

const (
	switchType = "switch"
)

const (
	observationIDField     = "observation_id"
	detectionDefinitionIDs = "detection_definitions.*.definition_id"
	runtimeComponentIDs    = "components.*.component_id"
)

const (
	targetField       = "target"
	defaultField      = "default"
	actionsSection    = "action_contracts"
	objectivesSection = "objectives"
	objectiveStep     = "objective"
	callStep          = "call"
	retryStep         = "retry"
)

const (
	parallelStepType = "parallel"
	joinStepType     = "join"
)

const (
	participantRefsField     = "participant_refs"
	participantRoleRefsField = "participant_role_refs"
	actionRefsField          = "action_contract_refs"
	boundaryRefsField        = "observation_boundary_refs"
	outcomeRefsField         = "outcome_interpretation_rule_refs"
	authorityScopeRefsField  = "authority_scope_refs"
	backendFeaturesField     = "backend_feature_support_refs"
	evidenceContractsField   = "evidence_contract_refs"
	evidenceRefsField        = "evidence_refs"
	observableRefsField      = "observable_refs"
	hiddenRefsField          = "hidden_refs"
	viewRulesField           = "view_rules"
	viewTransitionsField     = "view_transitions"
	informationRefField      = "information_ref"
	toolRefField             = "tool_ref"
	outcomeRulesSection      = "outcome_interpretation_rules"
)

const (
	scopeRefsField               = "scope_refs"
	revokedTerm                  = "revoked"
	proposalTerm                 = "proposal"
	controlTerm                  = "control"
	decisionTerm                 = "decision"
	evidenceRequirementRefsField = "evidence_requirement_refs"
)

const (
	protocolField           = "protocol"
	forestTrustField        = "forest_trust"
	identityFederationField = "identity_federation"
)

const (
	temporalConstraintsSection = "temporal_constraints"
	mailServicesField          = "mail_services"
)
