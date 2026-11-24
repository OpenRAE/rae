package processor

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func (state *compilerState) compileTimeModel() {
	model := state.input.model
	compiled := CompiledTimeModel{Domains: []TimeDomain{}, Clocks: []Clock{}, Mappings: []TimeMapping{}, ProgressionPolicies: []TimePolicy{}, Constraints: []TemporalConstraint{}}
	domains := fieldValue(model.TimeDomains)
	for _, name := range orderedNames(domains, state.names("time_domains")) {
		domain := domains[name]
		ratio := fieldValue(domain.TickPeriodSeconds)
		compiled.Domains = append(compiled.Domains, TimeDomain{Address: state.address("time", "domain", name), Kind: string(fieldValue(domain.Kind)), Epoch: string(fieldValue(domain.Epoch)), Visibility: string(fieldValue(domain.Visibility)), Description: fieldValue(domain.Description), TickNumerator: fieldValue(ratio.Numerator), TickDenominator: fieldValue(ratio.Denominator)})
	}
	clocks := fieldValue(model.Clocks)
	for _, name := range orderedNames(clocks, state.names("clocks")) {
		clock := clocks[name]
		compiled.Clocks = append(compiled.Clocks, Clock{Address: state.address("time", "clock", name), TimeDomainAddress: state.address("time", "domain", fieldValue(clock.TimeDomainRef)), AuthorityKind: string(fieldValue(clock.AuthorityKind)), AuthorityRef: fieldValue(clock.AuthorityRef), Monotonicity: string(fieldValue(clock.Monotonicity)), SupportsPause: fieldValue(clock.SupportsPause), SupportsReset: fieldValue(clock.SupportsReset), SupportsJump: fieldValue(clock.SupportsJump), Description: fieldValue(clock.Description)})
	}
	mappings := fieldValue(model.TimeDomainMappings)
	for _, name := range orderedNames(mappings, state.names("time_domain_mappings")) {
		mapping := mappings[name]
		scale := fieldValue(mapping.Scale)
		compiled.Mappings = append(compiled.Mappings, TimeMapping{Address: state.address("time", "mapping", name), SourceDomainAddress: state.address("time", "domain", fieldValue(mapping.SourceDomainRef)), TargetDomainAddress: state.address("time", "domain", fieldValue(mapping.TargetDomainRef)), Kind: string(fieldValue(mapping.MappingKind)), Description: fieldValue(mapping.Description), ScaleNumerator: fieldValue(scale.Numerator), ScaleDenominator: fieldValue(scale.Denominator), OffsetTicks: fieldValue(mapping.OffsetTicks)})
	}
	policies := fieldValue(model.TimeProgressionPolicies)
	for _, name := range orderedNames(policies, state.names("time_progression_policies")) {
		policy := policies[name]
		pacing := fieldValue(policy.PacingRatio)
		compiled.ProgressionPolicies = append(compiled.ProgressionPolicies, TimePolicy{Address: state.address("time", "policy", name), ClockAddress: state.address("time", "clock", fieldValue(policy.ClockRef)), AdvancementMode: string(fieldValue(policy.AdvancementMode)), SynchronizationMode: string(fieldValue(policy.SynchronizationMode)), ResetBehavior: string(fieldValue(policy.ResetBehavior)), ReplayBehavior: string(fieldValue(policy.ReplayBehavior)), Description: fieldValue(policy.Description), PacingNumerator: fieldValue(pacing.Numerator), PacingDenominator: fieldValue(pacing.Denominator), StepTicks: optionalNumber(fieldValue(policy.StepTicks)), DriftBoundTicks: optionalNumber(fieldValue(policy.DriftBoundTicks))})
	}
	constraints := fieldValue(model.TemporalConstraints)
	for _, name := range orderedNames(constraints, state.names("temporal_constraints")) {
		constraint := constraints[name]
		subjectAddresses := []string{}
		for _, ref := range fieldValue(constraint.SubjectRefs) {
			subjectAddresses = append(subjectAddresses, state.temporalSubject(ref))
		}
		startTick, startMicrostep := timeCoordinate(fieldValue(constraint.Start))
		endTick, endMicrostep := timeCoordinate(fieldValue(constraint.End))
		compiled.Constraints = append(compiled.Constraints, TemporalConstraint{Address: state.address("time", "constraint", name), Kind: string(fieldValue(constraint.ConstraintKind)), ClockAddress: state.address("time", "clock", fieldValue(constraint.ClockRef)), Description: fieldValue(constraint.Description), SubjectAddresses: subjectAddresses, StartTick: startTick, StartMicrostep: startMicrostep, EndTick: endTick, EndMicrostep: endMicrostep, DurationTicks: optionalNumber(fieldValue(constraint.DurationTicks)), CadenceTicks: optionalNumber(fieldValue(constraint.CadenceTicks))})
	}
	state.model.TimeModel = compiled
	state.model.HasTimeModel = len(compiled.Domains) > 0 || len(compiled.Clocks) > 0
}
func optionalNumber(raw json.RawMessage) *json.Number {
	if len(raw) == 0 || bytes.Equal(raw, []byte(termNull)) {
		return nil
	}
	var number json.Number
	if err := json.Unmarshal(raw, &number); err != nil {
		return nil
	}
	return &number
}
func timeCoordinate(raw json.RawMessage) (*json.Number, *json.Number) {
	if len(raw) == 0 || bytes.Equal(raw, []byte(termNull)) {
		return nil, nil
	}
	coordinate := struct {
		Tick      json.Number `json:"tick"`
		Microstep json.Number `json:"microstep"`
	}{Microstep: "0"}
	if err := json.Unmarshal(raw, &coordinate); err != nil {
		return nil, nil
	}
	return &coordinate.Tick, &coordinate.Microstep
}
func (state *compilerState) temporalSubject(ref string) string {
	// Canonical SDL declaration identity remains distinct from a planned resource.
	for _, name := range state.names(termBehaviorSpecifications) {
		prefix := "behavior_specifications." + name + ".participant_inject_deliveries."
		if after, ok := strings.CutPrefix(ref, prefix); ok {
			return state.address(termParticipant, termBehaviorSpecification, name, "inject-delivery", after)
		}
	}
	sections := []string{termNodes, "infrastructure", termFeatures, termConditions, termPropositions, termAssertions, "entities", termInjects, termEvents, termScripts, termStories, termContent, termGeneratedArtifacts, termPersistentVolumes, termAccounts, "identity_domains", "relationships", "agents", termActionContracts, termObservationBoundaries, termOutcomeInterpretationRules, termBehaviorSpecifications, "evidence_requirements", termObjectives, termWorkflows}
	for _, section := range sections {
		for _, name := range state.names(section) {
			if ref == name || ref == section+"."+name {
				return state.address("sdl", strings.ReplaceAll(section, "_", "-"), name)
			}
		}
	}
	if address := state.temporalWorkflowStepSubject(ref); address != "" {
		return address
	}
	state.err = invalidCompiled()
	return ""
}

func (state *compilerState) temporalWorkflowStepSubject(ref string) string {
	workflows := fieldValue(state.input.model.Workflows)
	for _, name := range orderedNames(workflows, state.names(termWorkflows)) {
		if suffix, found := strings.CutPrefix(ref, name+"."); found {
			if _, exists := fieldValue(workflows[name].Steps)[suffix]; exists {
				return state.address("sdl", "workflow-step", name, suffix)
			}
		}
	}
	return ""
}

// TimeModelContract projects compiled time facts into the published contract.
func TimeModelContract(input Compilation) (*binding.TimeModelV1, error) {
	admitted, err := nativeCompilation(input)
	if err != nil {
		return nil, err
	}
	model := admitted.model.view
	if !model.HasTimeModel {
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
	result, err := timeModelContract(model.TimeModel)
	return &result, err
}
func timeModelContract(input CompiledTimeModel) (binding.TimeModelV1, error) {
	// These are published wire projections of native typed time records.
	domains, clocks, mappings, policies, constraints := map[string]any{}, map[string]any{}, map[string]any{}, map[string]any{}, map[string]any{}
	ratio := func(numerator, denominator json.Number) any {
		return struct {
			Numerator   json.Number `json:"numerator"`
			Denominator json.Number `json:"denominator"`
		}{numerator, denominator}
	}
	for _, d := range input.Domains {
		domains[d.Address] = struct {
			Address           string `json:"address"`
			Kind              string `json:"kind"`
			TickPeriodSeconds any    `json:"tick_period_seconds"`
			Epoch             string `json:"epoch"`
			Visibility        string `json:"visibility"`
			Description       string `json:"description"`
		}{d.Address, d.Kind, ratio(d.TickNumerator, d.TickDenominator), d.Epoch, d.Visibility, d.Description}
	}
	for _, c := range input.Clocks {
		clocks[c.Address] = struct {
			Address           string `json:"address"`
			TimeDomainAddress string `json:"time_domain_address"`
			AuthorityKind     string `json:"authority_kind"`
			AuthorityRef      string `json:"authority_ref"`
			Monotonicity      string `json:"monotonicity"`
			SupportsPause     bool   `json:"supports_pause"`
			SupportsReset     bool   `json:"supports_reset"`
			SupportsJump      bool   `json:"supports_jump"`
			Description       string `json:"description"`
		}{c.Address, c.TimeDomainAddress, c.AuthorityKind, c.AuthorityRef, c.Monotonicity, c.SupportsPause, c.SupportsReset, c.SupportsJump, c.Description}
	}
	for _, m := range input.Mappings {
		mappings[m.Address] = struct {
			Address             string      `json:"address"`
			SourceDomainAddress string      `json:"source_domain_address"`
			TargetDomainAddress string      `json:"target_domain_address"`
			MappingKind         string      `json:"mapping_kind"`
			Scale               any         `json:"scale"`
			OffsetTicks         json.Number `json:"offset_ticks"`
			Description         string      `json:"description"`
		}{m.Address, m.SourceDomainAddress, m.TargetDomainAddress, m.Kind, ratio(m.ScaleNumerator, m.ScaleDenominator), m.OffsetTicks, m.Description}
	}
	for _, p := range input.ProgressionPolicies {
		policies[p.Address] = struct {
			Address             string       `json:"address"`
			ClockAddress        string       `json:"clock_address"`
			AdvancementMode     string       `json:"advancement_mode"`
			PacingRatio         any          `json:"pacing_ratio"`
			SynchronizationMode string       `json:"synchronization_mode"`
			StepTicks           *json.Number `json:"step_ticks"`
			DriftBoundTicks     *json.Number `json:"drift_bound_ticks"`
			ResetBehavior       string       `json:"reset_behavior"`
			ReplayBehavior      string       `json:"replay_behavior"`
			Description         string       `json:"description"`
		}{p.Address, p.ClockAddress, p.AdvancementMode, ratio(p.PacingNumerator, p.PacingDenominator), p.SynchronizationMode, p.StepTicks, p.DriftBoundTicks, p.ResetBehavior, p.ReplayBehavior, p.Description}
	}
	coordinate := func(tick, microstep *json.Number) any {
		if tick == nil {
			return nil
		}
		return struct {
			Tick      *json.Number `json:"tick"`
			Microstep *json.Number `json:"microstep"`
		}{tick, microstep}
	}
	for _, c := range input.Constraints {
		constraints[c.Address] = struct {
			Address          string       `json:"address"`
			Kind             string       `json:"kind"`
			ClockAddress     string       `json:"clock_address"`
			SubjectAddresses []string     `json:"subject_addresses"`
			Start            any          `json:"start"`
			End              any          `json:"end"`
			DurationTicks    *json.Number `json:"duration_ticks"`
			CadenceTicks     *json.Number `json:"cadence_ticks"`
			Description      string       `json:"description"`
		}{c.Address, c.Kind, c.ClockAddress, c.SubjectAddresses, coordinate(c.StartTick, c.StartMicrostep), coordinate(c.EndTick, c.EndMicrostep), c.DurationTicks, c.CadenceTicks, c.Description}
	}
	raw, err := json.Marshal(map[string]any{"schema_version": "time-model/v1", "domains": domains, "clocks": clocks, "mappings": mappings, "progression_policies": policies, "temporal_constraints": constraints})
	if err != nil {
		return binding.TimeModelV1{}, invalidCompiled()
	}
	var result binding.TimeModelV1
	err = json.Unmarshal(raw, &result)
	return result, err
}

// ScenarioComponentOptions derives component needs from native SDL compilation.
func ScenarioComponentOptions(scenario sdl.Scenario) (ComponentOptions, error) {
	compiled, err := Compile(scenario, nil)
	if err != nil {
		return ComponentOptions{}, err
	}
	return CompiledComponentOptions(compiled.Model())
}

// CompiledComponentOptions derives component needs from an admitted native model.
func CompiledComponentOptions(input RuntimeModel) (ComponentOptions, error) {
	admitted, err := nativeRuntimeModel(input)
	if err != nil {
		return ComponentOptions{}, err
	}
	model := admitted.view
	for _, finding := range model.Diagnostics {
		if finding.Severity == "error" {
			return ComponentOptions{}, invalidCompiled()
		}
	}
	options := ComponentOptions{WithTime: len(model.TimeModel.Clocks) > 0, WithObservation: len(model.ObservationDemands) > 0 || len(model.CaptureDemands) > 0}
	for _, resource := range model.Resources {
		if resource.Domain == termOrchestration {
			options.WithOrchestrator = true
		}
		if resource.Domain == termEvaluation {
			options.WithEvaluator = true
		}
	}
	for _, resource := range model.ParticipantResources {
		if resource.Kind == termBehaviorSpecification || resource.Kind == termParticipantBehavior {
			options.WithParticipantRuntime = true
		}
	}
	return options, nil
}
