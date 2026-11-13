package processor

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type compilerInput struct {
	scenario    sdl.Scenario
	model       binding.InstantiatedScenarioV1
	order       map[string][]string
	supplied    map[string]bool
	aliases     map[string][]string
	references  map[string]map[string][]string
	descriptive bool
}
type compilerState struct {
	input                compilerInput
	model                CompiledScenario
	err                  error
	runtimeReferences    map[string]string
	topology             compiledTopology
	knownNames           map[string]map[string]bool
	actions              map[string]participantAction
	outcomes             map[string]participantOutcomeRule
	boundaries           map[string]participantBoundary
	entities             map[string]entityMetadata
	participantRoles     map[string]string
	behaviors            map[string]participantBehavior
	tools                map[string]participantTool
	specifications       map[string]participantSpecification
	deliveries           map[string]participantDelivery
	contextByParticipant map[string][]controlContextSelection
	contextByOwner       map[string][]controlContextSelection
}

// Compile binds authored parameters through SDL admission and compiles once.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func Compile(scenario sdl.Scenario, parameters map[string]any) (Compilation, error) {
	return CompileWithOptions(scenario, CompileOptions{Parameters: parameters})
}

// CompileInstantiated compiles an already admitted concrete scenario.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func CompileInstantiated(scenario sdl.InstantiatedScenario) (Compilation, error) {
	if _, err := sdl.DocumentBytes(scenario); err != nil {
		return nil, err
	}
	return compileAdmitted(scenario, CompileOptions{}, false)
}

// CompileWithOptions instantiates and compiles SDL with explicit caller inputs.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func CompileWithOptions(scenario sdl.Scenario, options CompileOptions) (Compilation, error) {
	raw, err := sdl.DocumentBytes(scenario)
	if err != nil {
		return nil, err
	}
	var phase struct {
		MaterializationProvenance json.RawMessage `json:"materialization_provenance"`
	}
	if checkErr := json.Unmarshal(raw, &phase); checkErr != nil {
		return nil, invalidCompiled()
	}
	if phase.MaterializationProvenance != nil {
		return CompileMaterialized(scenario, options)
	}
	if instance, ok := scenario.(sdl.InstantiatedScenario); ok {
		return compileAdmitted(instance, options, false)
	}
	if len(options.Capture.EvidenceRelations) > 0 && options.Capture.RelationScenario == nil {
		options.Capture.RelationScenario = scenario
	}
	instance, err := sdl.Instantiate(scenario, options.Parameters)
	if err != nil {
		return nil, err
	}
	return compileAdmitted(instance, options, false)
}

// CompileMaterialized compiles an admitted materialization description for inspection.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func CompileMaterialized(scenario sdl.Scenario, options CompileOptions) (Compilation, error) {
	raw, err := sdl.DocumentBytes(scenario)
	if err != nil {
		return nil, err
	}
	var phase struct {
		MaterializationProvenance json.RawMessage `json:"materialization_provenance"`
	}
	if err := json.Unmarshal(raw, &phase); err != nil || len(phase.MaterializationProvenance) == 0 || bytes.Equal(phase.MaterializationProvenance, []byte(termNull)) {
		return nil, invalidCompiled()
	}
	if _, err := sdl.Validate(scenario); err != nil {
		return nil, err
	}
	return compileAdmitted(scenario, options, true)
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func compileAdmitted(scenario sdl.Scenario, options CompileOptions, descriptive bool) (Compilation, error) {
	state, err := newCompilerState(scenario, descriptive)
	if err != nil {
		return nil, err
	}
	if checkErr := state.admitProfileAuthority(options.ProfileAuthority); checkErr != nil {
		return nil, checkErr
	}
	state.compileDefinitions()
	state.compileMetadata()
	state.compileTimeModel()
	state.compileCapabilityConstraints()
	state.compileTopology()
	state.compileNodes()
	state.compileFeatureBindings()
	state.compilePropositions()
	state.compileEvidenceDemands(options.Capture)
	state.compileConditionBindings()
	state.compileInjects()
	state.compileInjectBindings()
	state.compileContentPlacements()
	state.compileDomainControllerPlacements()
	state.compileAccountPlacements()
	state.compileGeneratedArtifacts()
	state.compilePersistentVolumes()
	state.compileAssertions()
	state.compileRealization()
	state.compileActionContracts()
	state.compileObservationBoundaries()
	state.compileOutcomeRules()
	state.compileControlContexts()
	state.compileParticipantBehaviors()
	state.compileBehaviorSpecifications()
	state.compileToolAffordances()
	state.joinParticipantTools()
	state.compileParticipantDeliveries()
	state.compileEvents()
	state.compileScripts()
	state.compileStories()
	state.compileObjectives()
	state.compileWorkflows()
	state.compileExecutionPolicies()
	state.compileSelectedProfiles()
	if state.err != nil {
		return nil, state.err
	}
	document, err := compiledProjection(state.model)
	if err != nil {
		return nil, err
	}
	return &compilation{model: &runtimeModel{view: state.model, document: document, participants: compiledParticipants{actions: state.actions, outcomes: state.outcomes, boundaries: state.boundaries, behaviors: state.behaviors, specifications: state.specifications, tools: state.tools, deliveries: state.deliveries}}}, nil
}

func newCompilerState(scenario sdl.Scenario, descriptive bool) (compilerState, error) {
	raw, err := sdl.ModelBytes(scenario)
	if err != nil {
		return compilerState{}, err
	}
	var input binding.InstantiatedScenarioV1
	if checkErr := json.Unmarshal(raw, &input); checkErr != nil {
		return compilerState{}, invalidCompiled()
	}
	order, err := compileFieldOrder(raw)
	if err != nil {
		return compilerState{}, invalidCompiled()
	}
	aliases, err := sdl.ReferenceBindings(scenario)
	if err != nil {
		return compilerState{}, err
	}
	state := compilerState{input: compilerInput{scenario: scenario, model: input, order: order, supplied: map[string]bool{}, descriptive: descriptive}, model: CompiledScenario{Name: fieldValue(input.Name), Original: scenario, Diagnostics: []diagnostic.Diagnostic{}}}
	state.input.aliases = aliases
	state.model.Descriptive = descriptive
	state.model.AugmentationScopeRequired = !descriptive && input.AugmentationScope.Present() && !input.AugmentationScope.Null()
	if provenance, ok := input.InstantiationProvenance.Value(); ok {
		for _, record := range fieldValue(provenance.Explicitness) {
			state.input.supplied[fieldValue(record.ModelPath)] = true
		}
	}
	if descriptive {
		supplied, checkErr := sdl.DocumentBytes(scenario)
		if checkErr != nil {
			return compilerState{}, checkErr
		}
		state.input.supplied = materializedSuppliedPaths(supplied)
	}
	return state, nil
}

func (state *compilerState) admitProfileAuthority(supplied *binding.PlanRealizationProfilesV1) error {
	if supplied == nil {
		return nil
	}
	limits := ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}
	if err := admission.CheckTransport(supplied, limits); err != nil {
		return err
	}
	validator, err := processorAdmissionOwner()
	if err != nil {
		return err
	}
	encoded, err := json.Marshal(supplied)
	if err != nil {
		return invalidCompiled()
	}
	if err := validator.CheckPortable("plan-realization-profiles-v1", encoded, limits); err != nil {
		return err
	}
	state.model.ProfileAuthority = copyTransport(supplied)
	return nil
}

//nolint:ireturn // Each generated instantiation returns its concrete transport type without a runtime interface.
func fieldValue[T any](field binding.Field[T]) T { result, _ := field.Value(); return result }

func (state *compilerState) compileRealization() {
	state.model.RealizationRequirements = []realization.Requirement{}
	state.model.RealizationAuthority = []realization.Authority{}
	if state.input.descriptive {
		return
	}
	instance, ok := state.input.scenario.(sdl.InstantiatedScenario)
	if !ok {
		state.err = invalidCompiled()
		return
	}
	result, err := realization.Compile(instance)
	if err != nil {
		state.err = err
		return
	}
	state.model.RealizationRequirements = result.Requirements
	state.model.RealizationAuthority = result.Authority
	state.model.Diagnostics = append(state.model.Diagnostics, result.Diagnostics...)
}
func compileFieldOrder(raw []byte) (map[string][]string, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	order := compilerFieldOrder{decoder: decoder, result: map[string][]string{}}
	err := order.walk("")
	return order.result, err
}

type compilerFieldOrder struct {
	decoder *json.Decoder
	result  map[string][]string
}

func (order *compilerFieldOrder) walk(pointer string) error {
	token, err := order.decoder.Token()
	if err != nil {
		return err
	}
	delimiter, container := token.(json.Delim)
	if !container {
		return nil
	}
	switch delimiter {
	case '{':
		err = order.mapping(pointer)
	case '[':
		err = order.sequence(pointer)
	}
	if err != nil {
		return err
	}
	_, err = order.decoder.Token()
	return err
}
func (order *compilerFieldOrder) mapping(pointer string) error {
	order.result[pointer] = []string{}
	for order.decoder.More() {
		key, err := order.decoder.Token()
		if err != nil {
			return err
		}
		name, valid := key.(string)
		if !valid {
			return invalidCompiled()
		}
		order.result[pointer] = append(order.result[pointer], name)
		if err := order.walk(pointer + "/" + escapePointer(name)); err != nil {
			return err
		}
	}
	return nil
}
func (order *compilerFieldOrder) sequence(pointer string) error {
	for index := 0; order.decoder.More(); index++ {
		if err := order.walk(pointer + "/" + strconv.Itoa(index)); err != nil {
			return err
		}
	}
	return nil
}

func escapePointer(input string) string {
	return strings.ReplaceAll(strings.ReplaceAll(input, "~", "~0"), "/", "~1")
}
func orderedNames[T any](input map[string]T, known []string) []string {
	result := make([]string, 0, len(input))
	seen := make(map[string]bool, len(input))
	for _, name := range known {
		if _, exists := input[name]; exists && !seen[name] {
			result = append(result, name)
			seen[name] = true
		}
	}
	for _, name := range slices.Sorted(maps.Keys(input)) {
		if !seen[name] {
			result = append(result, name)
		}
	}
	return result
}
func (state *compilerState) names(section string) []string { return state.input.order["/"+section] }
func (state *compilerState) address(parts ...string) string {
	result, err := address.Render(parts...)
	if err != nil && state.err == nil {
		state.err = fault.New(fault.InvalidInput, "processor-resource-address", nil)
	}
	return result
}
func (state *compilerState) payload(input any) ResourcePayload {
	raw, err := json.Marshal(input)
	if err != nil && state.err == nil {
		state.err = fault.New(fault.InvalidInput, "processor-resource-projection", nil)
	}
	return ResourcePayload{data: raw}
}
func (state *compilerState) addDiagnostics(findings []diagnostic.Diagnostic) {
	state.model.Diagnostics = append(state.model.Diagnostics, findings...)
}
func compileDiagnostic(code, domain, addr, message string) diagnostic.Diagnostic {
	return diagnostic.Diagnostic{Code: code, Domain: domain, Address: addr, Message: message, Severity: "error"}
}
func dedupe(input []string) []string {
	result := make([]string, 0, len(input))
	seen := make(map[string]bool, len(input))
	for _, item := range input {
		if !seen[item] {
			seen[item] = true
			result = append(result, item)
		}
	}
	return result
}
func rawJSON(input any) json.RawMessage {
	raw, err := json.Marshal(input)
	if err != nil {
		panic("processor: invalid owned input projection")
	}
	return raw
}
func rawString(input json.RawMessage) string {
	var result string
	_ = json.Unmarshal(input, &result)
	return result
}
func materializedSuppliedPaths(raw []byte) map[string]bool {
	order, err := compileFieldOrder(raw)
	if err != nil {
		return nil
	}
	result := map[string]bool{}
	for pointer, fields := range order {
		prefix := strings.TrimPrefix(pointer, "/")
		prefix = strings.ReplaceAll(strings.ReplaceAll(strings.ReplaceAll(prefix, "/", "."), "~1", "/"), "~0", "~")
		for _, field := range fields {
			name := field
			if prefix != "" {
				name = prefix + "." + field
			}
			result[name] = true
		}
	}
	return result
}

func (state *compilerState) compileDefinitions() {
	model := state.input.model
	add := func(_ string, kind string, entries []string, payload func(string) json.RawMessage) {
		for _, name := range entries {
			state.model.Definitions = append(state.model.Definitions, Definition{Address: state.address("template", kind, name), Name: name, Kind: kind, Payload: ResourcePayload{data: payload(name)}})
		}
	}
	features := fieldValue(model.Features)
	add(termFeatures, "feature", orderedNames(features, state.names(termFeatures)), func(name string) json.RawMessage { return rawJSON(features[name]) })
	conditions := fieldValue(model.Conditions)
	add(termConditions, "condition", orderedNames(conditions, state.names(termConditions)), func(name string) json.RawMessage { return rawJSON(conditions[name]) })
	injects := fieldValue(model.Injects)
	add(termInjects, termInject, orderedNames(injects, state.names(termInjects)), func(name string) json.RawMessage { return rawJSON(injects[name]) })
}
