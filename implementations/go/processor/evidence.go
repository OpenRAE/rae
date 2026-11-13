package processor

import (
	"encoding/json"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type evidenceSelector struct {
	Scope      string       `json:"semantic_scope"`
	Excluded   []string     `json:"excluded_scopes"`
	Components []string     `json:"component_refs"`
	Kind       string       `json:"data_kind"`
	Names      []string     `json:"names"`
	Windows    []string     `json:"window_refs"`
	Coverage   *string      `json:"coverage_profile"`
	MaxItems   *json.Number `json:"max_items"`
}
type evidenceObservationRule struct {
	ID         string            `json:"rule_id"`
	Scope      string            `json:"scope"`
	Purpose    string            `json:"purpose"`
	Mode       *string           `json:"mode"`
	Selector   *evidenceSelector `json:"selector"`
	Collection *string           `json:"collection"`
	Retention  *string           `json:"retention"`
	Export     *string           `json:"export"`
	Basis      *string           `json:"basis"`
	Redaction  *string           `json:"redaction"`
	Integrity  *string           `json:"integrity"`
	Prohibited []string          `json:"prohibited_stages"`
	Required   bool              `json:"required"`
	Authority  string            `json:"authority_ref"`
}
type evidenceSource struct {
	SourceRefs            []string                 `json:"source_refs"`
	ScopeRefs             []string                 `json:"scope_refs"`
	SourceClass           string                   `json:"source_class"`
	Scope                 string                   `json:"scope"`
	Channel               string                   `json:"channel"`
	ChannelRefs           []string                 `json:"channel_refs"`
	Window                string                   `json:"window"`
	Trigger               string                   `json:"trigger_ref"`
	Boundary              string                   `json:"boundary_ref"`
	BoundaryKind          string                   `json:"boundary_kind"`
	OutputContract        string                   `json:"output_contract"`
	FieldSelectors        []string                 `json:"field_selectors"`
	ArtifactRole          string                   `json:"artifact_role"`
	MediaTypes            []string                 `json:"media_types"`
	Integrity             string                   `json:"integrity"`
	Sensitivity           string                   `json:"sensitivity"`
	Redaction             string                   `json:"redaction"`
	Retention             string                   `json:"retention"`
	CaptureSpecRef        string                   `json:"capture_spec_ref"`
	CaptureRequirementRef string                   `json:"capture_requirement_ref"`
	Observation           *evidenceObservationRule `json:"observation_demand"`
}

//go:fix inline
func evidenceValues(values ...string) []string {
	result := []string{}
	for _, value := range values {
		if value != "" {
			result = append(result, value)
		}
	}
	return result
}
func (state *compilerState) observationProfiles() []admission.RealizationCollectionProfile {
	result := []admission.RealizationCollectionProfile{}
	for _, descriptor := range realization.ConcernDescriptors() {
		if len(descriptor.IdentityFields) == 0 {
			continue
		}
		for _, name := range state.names(descriptor.Section) {
			path := append([]string{descriptor.Section, name}, descriptor.AuthoredPath...)
			result = append(result, admission.RealizationCollectionProfile{FieldPointer: jsonpointer.FromTokens(path), CollectionKind: descriptor.Kind, IdentityFields: descriptor.IdentityFields, Closure: admission.RealizationClosure{Posture: "closed", Universe: "sdl-collection-members/v1", Profile: "recursive-realization-constraint/v1"}})
		}
	}
	return result
}
func (state *compilerState) observationComponents(refs []string, required bool) ([]string, error) {
	aliases, loaded := state.input.references[termObservationSubject]
	if !loaded {
		var err error
		aliases, err = sdl.ReferenceBindingsFor(state.input.scenario, termObservationSubject)
		if err != nil {
			return nil, err
		}
		if state.input.references == nil {
			state.input.references = map[string]map[string][]string{}
		}
		state.input.references[termObservationSubject] = aliases
	}
	result := []string{}
	for _, ref := range refs {
		candidates := aliases[ref]
		if len(candidates) != 1 {
			return nil, invalidCompiled()
		}
		address := state.runtimeDeclaration(candidates[0])
		if required && address == "" {
			return nil, invalidCompiled()
		}
		if address != "" {
			result = append(result, address)
		}
	}
	return dedupe(result), nil
}
func (state *compilerState) canonicalEvidenceRule(rule evidenceObservationRule, profiles []admission.RealizationCollectionProfile) (evidenceObservationRule, error) {
	if rule.Authority != "" && rule.Authority != "author" {
		return evidenceObservationRule{}, invalidCompiled()
	}
	rule.Authority = "author"
	pointers := []string{rule.Scope}
	if rule.Selector != nil {
		pointers = append(pointers, rule.Selector.Scope)
		pointers = append(pointers, rule.Selector.Excluded...)
	}
	scopes, err := sdl.ObservationScopes(state.input.scenario, dedupe(pointers), nil, profiles)
	if err != nil {
		return evidenceObservationRule{}, err
	}
	rule.Scope = scopes[rule.Scope]
	if rule.Selector != nil {
		rule.Selector.Scope = scopes[rule.Selector.Scope]
		for i, excluded := range rule.Selector.Excluded {
			rule.Selector.Excluded[i] = scopes[excluded]
		}
		rule.Selector.Components, err = state.observationComponents(rule.Selector.Components, true)
		if err != nil {
			return evidenceObservationRule{}, err
		}
		rule.Selector.Excluded = nonNilStrings(rule.Selector.Excluded)
		rule.Selector.Windows = nonNilStrings(rule.Selector.Windows)
	}
	rule.Prohibited = nonNilStrings(rule.Prohibited)
	return rule, nil
}
func (state *compilerState) legacyEvidenceRules(name string, source evidenceSource, profiles []admission.RealizationCollectionProfile) ([]evidenceObservationRule, error) {
	components, err := state.observationComponents(source.SourceRefs, false)
	if err != nil {
		return nil, err
	}
	refs := source.ScopeRefs
	if len(refs) == 0 {
		refs = source.SourceRefs
	}
	scopes, err := sdl.ObservationScopes(state.input.scenario, nil, dedupe(refs), profiles)
	if err != nil {
		return nil, err
	}
	paths := []string{}
	for _, ref := range refs {
		paths = append(paths, scopes[ref])
	}
	if len(paths) == 0 {
		paths = []string{""}
	}
	channel := source.Channel
	if channel == "" {
		channel = "evidence"
	}
	retention := "require"
	if source.Retention == "not_retained" {
		retention = "disable"
	}
	result := []evidenceObservationRule{}
	for position, scope := range paths {
		id := name
		if len(paths) > 1 {
			id += ":" + strconv.Itoa(position)
		}
		result = append(result, evidenceObservationRule{ID: id, Scope: scope, Purpose: "experimental", Mode: new("selected"), Selector: &evidenceSelector{Scope: scope, Excluded: []string{}, Components: components, Kind: "stream", Names: []string{channel}, Windows: evidenceValues(source.Window, source.Trigger, source.Boundary)}, Collection: new("require"), Retention: new(retention), Export: new("disable"), Redaction: new(source.Redaction), Integrity: new(source.Integrity), Prohibited: []string{}, Authority: "evidence_requirements." + name})
	}
	return result, nil
}
func (state *compilerState) compileEvidenceDemands(inputs CaptureInputs) {
	if state.input.descriptive {
		if state.err == nil && (len(inputs.CaptureSpecs) > 0 || len(inputs.EvidenceRelations) > 0) {
			state.model.CaptureDemands, state.err = CompileCaptureDemands(state.input.scenario, inputs)
		}
		return
	}
	state.model.CaptureDemands = []CaptureDemand{}
	state.model.ObservationDemands = []ObservationDemand{}
	sources, rules := state.compileEvidenceSources()
	if state.err != nil {
		return
	}
	state.compileCaptureDemands(sources, inputs)
	state.compileObservationDemands(rules)
}
func (state *compilerState) compileEvidenceSources() (map[string]evidenceSource, []evidenceObservationRule) {
	declarations := fieldValue(state.input.model.EvidenceRequirements)
	sources := map[string]evidenceSource{}
	rules := []evidenceObservationRule{}
	profiles := state.observationProfiles()
	for _, name := range state.names("evidence_requirements") {
		var source evidenceSource
		if json.Unmarshal(rawJSON(declarations[name]), &source) != nil {
			state.err = invalidCompiled()
			return nil, nil
		}
		sources[name] = source
		if source.Observation != nil {
			rule, err := state.canonicalEvidenceRule(*source.Observation, profiles)
			if err != nil {
				state.err = err
				return nil, nil
			}
			rules = append(rules, rule)
		} else {
			legacy, err := state.legacyEvidenceRules(name, source, profiles)
			if err != nil {
				state.err = err
				return nil, nil
			}
			rules = append(rules, legacy...)
		}
	}
	return sources, rules
}
func scenarioCaptureDemandValues(sources map[string]evidenceSource) []CaptureDemand {
	result := []CaptureDemand{}
	names := make([]string, 0, len(sources))
	for name := range sources {
		names = append(names, name)
	}
	slices.Sort(names)
	for _, name := range names {
		source := sources[name]
		if source.Observation == nil || source.Observation.Required {
			demand := compileCaptureDemand(name, source)
			result = append(result, demand)
		}
	}
	return result
}
func (state *compilerState) compileCaptureDemands(sources map[string]evidenceSource, inputs CaptureInputs) {
	demands, err := conjoinCaptureDemandInputs(state.input.scenario, inputs, scenarioCaptureDemandValues(sources))
	if err != nil {
		state.err = err
		return
	}
	state.model.CaptureDemands = demands
}
func (state *compilerState) compileObservationDemands(rules []evidenceObservationRule) {
	if len(rules) == 0 {
		return
	}
	raw := rawJSON(struct {
		Version string                    `json:"schema_version"`
		ID      string                    `json:"document_id"`
		Profile string                    `json:"scope_profile"`
		Rules   []evidenceObservationRule `json:"rules"`
	}{"observation-demand/v1", "scenario:" + state.model.Name, "recursive-realization-constraint/v1", rules})
	var document binding.ObservationDemandV1
	if json.Unmarshal(raw, &document) != nil {
		state.err = invalidCompiled()
		return
	}
	scopes := []string{}
	for _, rule := range rules {
		scopes = append(scopes, rule.Scope)
		if rule.Selector != nil {
			scopes = append(scopes, rule.Selector.Scope)
		}
	}
	scopes = dedupe(scopes)
	owner, err := processorAdmissionOwner()
	if err != nil {
		state.err = err
		return
	}
	normalized, err := admission.NormalizeObservationDemands(owner, document, scopes, admission.DefaultConstraintLimits())
	if err != nil {
		state.err = err
		return
	}
	if len(normalized.Diagnostics) > 0 {
		state.err = invalidCompiled()
		return
	}
	for _, demand := range normalized.Effective {
		state.model.ObservationDemands = append(state.model.ObservationDemands, ObservationDemand{Demand: demand, Payload: state.payload(demand.Document())})
	}
}
func compileCaptureDemand(name string, source evidenceSource) CaptureDemand {
	kind := map[string]string{"packet_capture": "packet-capture", termLog: termLog, termTrace: termTrace, "metric": "telemetry", "file_artifact": "artifact", "screen_capture": "artifact", "api_response": termObservation, "database_record": termObservation, "participant_output": termObservation, termOther: termOther}[source.Channel]
	channel := map[string]string{"packet_capture": "packet-capture", termLog: termBackendLog, termTrace: termBackendLog, "metric": "runtime-snapshot", "file_artifact": termFileArtifact, "screen_capture": termFileArtifact, "api_response": "participant-observation", "database_record": termFileArtifact, "participant_output": "participant-observation", termOther: termBackendLog}[source.Channel]
	windows := evidenceValues(source.Window)
	if source.Trigger != "" {
		windows = append(windows, termEvent)
	}
	windows = append(windows, evidenceValues(source.BoundaryKind)...)
	disclosure := termRedacted
	var redaction *string
	if source.Redaction == termNone {
		disclosure = "full"
	} else {
		redaction = new(source.Redaction)
	}
	return CaptureDemand{DemandID: name, Address: "evidence_requirements." + name, OutputContract: source.OutputContract, FieldSelectors: nonNilStrings(source.FieldSelectors), ArtifactRoles: evidenceValues(source.ArtifactRole), MediaTypes: nonNilStrings(source.MediaTypes), CaptureKind: kind, SourceClasses: evidenceValues(source.SourceClass), SourceRefs: nonNilStrings(source.SourceRefs), Scopes: evidenceValues(source.Scope), ScopeRefs: nonNilStrings(source.ScopeRefs), ChannelKinds: evidenceValues(channel), ChannelRefs: nonNilStrings(source.ChannelRefs), WindowKinds: windows, IntegrityModes: evidenceValues(source.Integrity), Sensitivity: source.Sensitivity, Disclosure: disclosure, RetentionPolicyRefs: evidenceValues(source.Retention), ExportPolicy: "not-required", RedactionPolicy: redaction, CaptureSpecRef: source.CaptureSpecRef, CaptureRequirementRef: source.CaptureRequirementRef}
}
func captureDemandProjection(demand CaptureDemand) map[string]any {
	return map[string]any{"demand_id": demand.DemandID, termAddress: demand.Address, "output_contract": demand.OutputContract, "field_selectors": demand.FieldSelectors, "artifact_roles": demand.ArtifactRoles, "media_types": demand.MediaTypes, "capture_kind": demand.CaptureKind, "source_classes": demand.SourceClasses, "source_refs": demand.SourceRefs, "scopes": demand.Scopes, "scope_refs": demand.ScopeRefs, "channel_kinds": demand.ChannelKinds, "channel_refs": demand.ChannelRefs, "window_kinds": demand.WindowKinds, "integrity_modes": demand.IntegrityModes, "sensitivity": demand.Sensitivity, "disclosure": demand.Disclosure, "retention_policy_refs": demand.RetentionPolicyRefs, "export_policy": demand.ExportPolicy, "redaction_policy": demand.RedactionPolicy, "capture_spec_ref": demand.CaptureSpecRef, "capture_requirement_ref": demand.CaptureRequirementRef}
}
