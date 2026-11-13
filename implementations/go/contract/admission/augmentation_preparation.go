package admission

import (
	"encoding/json"
	"maps"
	"reflect"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type augmentationLocation struct {
	path      string
	namespace []string
}
type augmentationResolver struct {
	content   *materializationCompiled
	cache     map[string]augmentationLocation
	remaining *int
}
type augmentationAdmission struct {
	plan, report, policy  any
	original, prospective *augmentationResolver
	rules                 []materializationScopeRule
	differences           []any
	remaining             int
}

// CheckAugmentationPreparation checks a prospective report against independent
// execution and native content projections. It grants no actual-world claim.
func CheckAugmentationPreparation(v *Validator, report binding.BackendAugmentationScopeV1, request validation.Value, manifest binding.BackendManifestV2, previous binding.RuntimeSnapshotV1, original, prospective MaterializationCompilation) ([]diagnostic.Diagnostic, error) {
	if v == nil || augmentationReportBounds(report) != nil {
		return nil, invalid()
	}
	plan, err := augmentationPlan(request)
	if err != nil {
		return nil, err
	}
	proposal, err := portableInventoryTransport(v, termBackendAugmentationScopeV1, report)
	if err != nil {
		return nil, err
	}
	if err := augmentationBinding(v, proposal, plan, request.ContractID(), manifest, previous); err != nil {
		return nil, err
	}
	admission := &augmentationAdmission{plan: plan, report: proposal, remaining: 100000}
	if err := admission.content(original, prospective); err != nil {
		return nil, err
	}
	return admission.effects()
}

func augmentationReportBounds(report binding.BackendAugmentationScopeV1) error {
	if err := CheckTransport(report, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}); err != nil {
		return err
	}
	effects, _ := report.Effects.Value()
	work := 0
	for _, effect := range effects {
		references, _ := effect.RequirementRefs.Value()
		scopes, _ := effect.AffectedScopes.Value()
		if err := augmentationScopeWork(&work, len(references), len(scopes)); err != nil {
			return err
		}
	}
	content, _ := report.Content.Value()
	commitment, _ := report.BindingDigest.Value()
	contract, _ := report.ContractId.Value()
	profile, _ := report.CoverageProfile.Value()
	projection := transportProjection{limits: value.Runtime(), bytes: 8 << 20}
	input := map[string]any{termEffects: transportValue{reflect.ValueOf(effects), false}, "content": value.DeclaredDocument(content), "binding_digest": commitment, termContractID: contract, "coverage_profile": profile}
	return value.ValidateProjected(input, value.Runtime(), func(input any) (any, error) {
		if _, typed := input.(transportValue); typed {
			return projection.project(input)
		}
		return input, nil
	})
}

func augmentationPlan(request validation.Value) (any, error) {
	switch request.ContractID() {
	case termProvisioningPlanV1, termOrchestrationPlanV1, termEvaluationPlanV1:
		return materializationAdmitted(request, request.ContractID())
	default:
		return nil, invalid()
	}
}

func augmentationBinding(v *Validator, report, plan any, contract string, manifest binding.BackendManifestV2, previous binding.RuntimeSnapshotV1) error {
	if at(plan, "materialization_source") == nil || stringAt(plan, "operation_id") == "" {
		return invalid()
	}
	normalized, err := NormalizeBackendManifest(v, manifest)
	if err != nil {
		return err
	}
	target, err := materializationJSON(augmentationJSON(normalized))
	if err != nil || at(target, "realization_envelope") == nil {
		return invalid()
	}
	snapshot, err := portableInventoryTransport(v, termRuntimeSnapshotV1, previous)
	if err != nil {
		return err
	}
	if factoryErr := augmentationSnapshotFactories(snapshot, previous); factoryErr != nil {
		return factoryErr
	}
	delete(snapshot, termSchemaVersion)
	planDigest, err := jsonDigest(map[string]any{fieldDomain: map[string]string{termProvisioningPlanV1: termProvisioning, termOrchestrationPlanV1: termOrchestration, termEvaluationPlanV1: termEvaluation}[contract], termPlan: augmentationPlanProjection(plan, contract)})
	if err != nil {
		return err
	}
	predecessor, err := jsonDigest(snapshot)
	if err != nil {
		return err
	}
	commitment, err := jsonDigest(map[string]any{termProfile: termBackendAugmentationScopeV1, termPlan: planDigest, termPredecessor: predecessor, termManifest: target})
	if err != nil {
		return err
	}
	return require(commitment == stringAt(report, "binding_digest"))
}

// These are model collection factories and nullable model header fields. An
// operation's arbitrary payload and explicit profile values remain untouched.
func augmentationPlanProjection(plan any, contract string) any {
	projected := object(materializationPlanProjection(plan))
	factoryFields(projected, []string{"operations", "diagnostics", "observation_demands"}, nil)
	if contract == termProvisioningPlanV1 {
		factoryFields(projected, []string{"realization_authority", "realization_constraints"}, nil)
	} else {
		factoryFields(projected, []string{"startup_order"}, nil)
	}
	operations := make([]any, 0, len(array(at(projected, "operations"))))
	for _, input := range array(at(projected, "operations")) {
		operation := maps.Clone(object(input))
		factoryFields(operation, []string{termOrderingDependencies, termRefreshDependencies}, nil)
		for _, key := range []string{"profile_bindings", "execution_policy_scopes"} {
			if len(array(operation[key])) == 0 {
				delete(operation, key)
			}
		}
		omitManifestNulls(operation, []string{"execution_policy"})
		operations = append(operations, operation)
	}
	projected["operations"] = operations
	return projected
}

// The native RuntimeSnapshot dataclass constructs empty root collections and
// entry dependency/profile tuples. Their published schemas omit factories;
// the existing generated field/projector owner supplies each concrete kind.
func augmentationSnapshotFactories(snapshot map[string]any, native binding.RuntimeSnapshotV1) error {
	record := reflect.ValueOf(native)
	for index := range record.NumField() {
		name, stored, _, err := transportField(record, index)
		if err != nil {
			return err
		}
		if _, present := snapshot[name]; present || stored.Type().Elem() == reflect.TypeFor[json.RawMessage]() {
			continue
		}
		kind := stored.Type().Elem().Kind()
		if kind == reflect.Map {
			snapshot[name] = map[string]any{}
			continue
		}
		if kind == reflect.Slice {
			snapshot[name] = []any{}
		}
	}
	for _, entry := range object(snapshot["entries"]) {
		factoryFields(object(entry), []string{termOrderingDependencies, termRefreshDependencies, "profile_bindings"}, nil)
	}
	return nil
}

func augmentationJSON(input any) []byte {
	raw, err := json.Marshal(input)
	if err != nil {
		panic("admission: invalid owned augmentation projection")
	}
	return raw
}

func (a *augmentationAdmission) content(original, prospective MaterializationCompilation) error {
	source, err := materializationContentInput(original)
	if err != nil {
		return err
	}
	selected, err := materializationContentInput(prospective)
	if err != nil {
		return err
	}
	a.original = &augmentationResolver{content: source, cache: map[string]augmentationLocation{}, remaining: &a.remaining}
	a.prospective = &augmentationResolver{content: selected, cache: map[string]augmentationLocation{}, remaining: &a.remaining}
	bound, err := materializationSource(at(a.plan, "materialization_source"))
	if err != nil || !equal(augmentationCommon(at(bound, planeScenario)), augmentationCommon(source.document)) {
		return invalid()
	}
	proposed, err := materializationJSON([]byte(stringAt(a.report, "content")))
	if err != nil || !equal(proposed, selected.document) || !matchingFields(source.full, selected.full, "augmentation_scope", "evidence_requirements") {
		return invalid()
	}
	profiles := materializationComposer{identities: source.identities}
	if err := profiles.mergeProfiles(selected.identities); err != nil {
		return err
	}
	difference := materializationDiff{identities: profiles.identities, remaining: 100000}
	if err := difference.walk(materializationOperand{value: source.full, present: true}, materializationOperand{value: selected.full, present: true}); err != nil {
		return err
	}
	a.differences = difference.origins
	a.policy = at(source.full, "augmentation_scope")
	for _, rule := range array(at(a.policy, termScopes)) {
		location, err := a.original.resolve(stringAt(rule, processLimitScopeField))
		if err != nil {
			return err
		}
		a.rules = append(a.rules, materializationScopeRule{path: location.path, permission: stringAt(rule, "permission"), namespace: stringsOf(at(rule, termNamespace))})
	}
	return nil
}

func augmentationCommon(input any) any {
	common := maps.Clone(object(input))
	delete(common, "instantiation_provenance")
	delete(common, "materialization_provenance")
	return common
}

func (r *augmentationResolver) resolve(pointer string) (augmentationLocation, error) {
	if location, cached := r.cache[pointer]; cached {
		return location, nil
	}
	path, namespace, err := materializationSemanticAddress(r.content, pointer, r.remaining)
	if err != nil {
		return augmentationLocation{}, err
	}
	location := augmentationLocation{path, namespace}
	r.cache[pointer] = location
	return location, nil
}

func (a *augmentationAdmission) effects() ([]diagnostic.Diagnostic, error) {
	effects := controlRows(at(a.report, termEffects), termFieldPointer)
	coverage := map[string]bool{}
	for _, difference := range a.differences {
		coverage[stringAt(difference, termFieldPointer)] = true
	}
	if !equalSet(coverage, keySet(effects)) {
		return nil, invalid()
	}
	for _, difference := range a.differences {
		findings, err := a.effect(difference, effects[stringAt(difference, termFieldPointer)])
		if err != nil || len(findings) > 0 {
			return findings, err
		}
	}
	return []diagnostic.Diagnostic{}, nil
}

func (a *augmentationAdmission) effect(difference, effect any) ([]diagnostic.Diagnostic, error) {
	for _, reference := range stringsOf(at(effect, "requirement_refs")) {
		if err := a.requirement(reference); err != nil {
			return nil, err
		}
	}
	resolver := a.prospective
	if stringAt(difference, "change") == termRemoved {
		resolver = a.original
	}
	ordinary := materializationInventory{execution: materializationExecution{original: a.original.content, plan: a.plan}}
	for _, pointer := range append([]string{stringAt(difference, termFieldPointer)}, stringsOf(at(effect, "affected_scopes"))...) {
		location, err := resolver.resolve(pointer)
		if err != nil {
			return nil, err
		}
		if location.path == stringAt(difference, termFieldPointer) && ordinary.ordinarySelection(difference) {
			continue
		}
		permission, governing, err := a.decision(location)
		if err != nil {
			return nil, err
		}
		if permission == termClosed {
			return augmentationScopeDiagnostics(effect, difference, governing), nil
		}
	}
	return nil, nil
}

func (a *augmentationAdmission) requirement(reference string) error {
	if reference == "backend-operational" {
		return nil
	}
	tokens := jsonpointer.Tokens(reference)
	if len(tokens) != 2 || !set([]any{"evidence_requirements", "objectives", "assertions", "propositions"})[tokens[0]] {
		return invalid()
	}
	_, err := a.original.resolve(reference)
	return err
}

func (a *augmentationAdmission) decision(location augmentationLocation) (string, string, error) {
	permission, governing := materializationScopeDecision(a.policy, a.rules, location.path, location.namespace)
	if a.policy == nil || permission == termClosed {
		return permission, governing, nil
	}
	for _, rule := range a.rules {
		a.remaining--
		if a.remaining < 0 {
			return "", "", invalid()
		}
		if !materializationScopeContains(location.path, rule.path) {
			continue
		}
		child, err := a.original.resolve(rule.path)
		if err != nil {
			return "", "", err
		}
		if childPermission, childGoverning := materializationScopeDecision(a.policy, a.rules, rule.path, child.namespace); childPermission == termClosed {
			return childPermission, childGoverning, nil
		}
	}
	return permission, governing, nil
}

func augmentationScopeDiagnostics(effect, difference any, governing string) []diagnostic.Diagnostic {
	if governing == "" {
		governing = "/"
	}
	findings := []diagnostic.Diagnostic{}
	for _, reference := range stringsOf(at(effect, "requirement_refs")) {
		findings = append(findings, diagnostic.Diagnostic{Code: "augmentation.scope-closed", Domain: "augmentation", Address: stringAt(difference, termFieldPointer), Severity: termError, Message: "Requirement " + augmentationTruncate(reference, 120) + " needs " + stringAt(difference, "change") + " " + augmentationTruncate(stringAt(difference, termFieldPointer), 160) + "; augmentation scope " + augmentationTruncate(governing, 120) + " is closed."})
	}
	return findings
}

func augmentationTruncate(text string, maximum int) string {
	runes := []rune(text)
	return string(runes[:min(len(runes), maximum)])
}
