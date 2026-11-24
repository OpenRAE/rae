package processor

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"
)

type participantFailureMapping struct {
	BackendErrorCode string `json:"backend_error_code"`
	FailureClass     string `json:"failure_class"`
	Diagnostic       string `json:"diagnostic"`
}
type participantTimingDisclosure struct {
	DisclosureID        string   `json:"disclosure_id"`
	DisclosureKind      string   `json:"disclosure_kind"`
	SupportMode         string   `json:"support_mode"`
	Description         string   `json:"description"`
	AffectedTemporalIDs []string `json:"affected_temporal_ids"`
	Limitations         []string `json:"limitations"`
}
type participantAction struct {
	arguments                     []participantArgument
	preconditions                 []participantConditionDeclaration
	effects                       []participantEffectDeclaration
	temporal                      []participantTemporalDeclaration
	Name                          string                        `json:"name"`
	Spec                          json.RawMessage               `json:"spec"`
	ActionName                    string                        `json:"action_name"`
	ArgumentShapeRef              string                        `json:"argument_shape_ref"`
	ArgumentDefinitions           []json.RawMessage             `json:"argument_definitions"`
	SemanticVersion               string                        `json:"semantic_version"`
	LifecycleState                string                        `json:"lifecycle_state"`
	BehavioralGranularity         string                        `json:"behavioral_granularity"`
	PreconditionClasses           []string                      `json:"precondition_classes"`
	EffectClasses                 []string                      `json:"effect_classes"`
	FailureClasses                []string                      `json:"failure_classes"`
	BackendFailureMappings        []participantFailureMapping   `json:"backend_failure_mappings"`
	InteractionClasses            []string                      `json:"interaction_classes"`
	SharedStateRefs               []string                      `json:"shared_state_refs"`
	CommutativeInteractionTargets []string                      `json:"commutative_interaction_targets"`
	MergeRuleRefs                 []string                      `json:"merge_rule_refs"`
	TemporalContractIDs           []string                      `json:"temporal_contract_ids"`
	TemporalKinds                 []string                      `json:"temporal_kinds"`
	TimeDomains                   []string                      `json:"time_domains"`
	ClockAuthorities              []string                      `json:"clock_authorities"`
	BackendTimingDisclosures      []participantTimingDisclosure `json:"backend_timing_disclosures"`
}

func (state *compilerState) compileActionContracts() {
	contracts := fieldValue(state.input.model.ActionContracts)
	work := participantWork{remaining: participantRelationWork}
	state.actions = map[string]participantAction{}
	for _, name := range orderedNames(contracts, state.names(termActionContracts)) {
		source := contracts[name]
		address := state.address(termParticipant, termActionContract, name)
		arguments := fieldValue(source.Arguments)
		if arguments == nil {
			arguments = map[string]json.RawMessage{}
		}
		shape := state.canonicalDigest(rawJSON(arguments))
		output := participantAction{Name: name, Spec: rawJSON(source), ActionName: name, ArgumentShapeRef: address + ".argument-shape.sha256-" + strings.TrimPrefix(shape, "sha256:"), ArgumentDefinitions: []json.RawMessage{}, SemanticVersion: fieldValue(source.SemanticVersion), LifecycleState: string(fieldValue(source.LifecycleState)), BehavioralGranularity: string(fieldValue(source.BehavioralGranularity)), PreconditionClasses: []string{}, EffectClasses: []string{}, FailureClasses: []string{}, BackendFailureMappings: []participantFailureMapping{}, InteractionClasses: []string{}, SharedStateRefs: []string{}, CommutativeInteractionTargets: []string{}, MergeRuleRefs: []string{}, TemporalContractIDs: []string{}, TemporalKinds: []string{}, TimeDomains: []string{}, ClockAuthorities: []string{}, BackendTimingDisclosures: []participantTimingDisclosure{}}
		if err := output.compileArguments(arguments, &work); err != nil {
			state.err = err
			return
		}
		state.compileActionClasses(name, &output)
		state.compileActionInteractions(name, &output)
		state.compileActionTiming(name, &output)
		output.uniqueTerms()
		state.actions[address] = output
		state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: name, Domain: termParticipant, Kind: termActionContract, Payload: state.payload(output)})
	}
}

func (output *participantAction) compileArguments(arguments map[string]json.RawMessage, work *participantWork) error {
	if !work.spend(len(arguments)) {
		return invalidCompiled()
	}
	for _, name := range slices.Sorted(maps.Keys(arguments)) {
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(arguments[name], &fields); err != nil {
			return invalidCompiled()
		}
		fields["name"] = rawJSON(name)
		definition := rawJSON(fields)
		compiled, err := compileParticipantArgument(definition)
		if err != nil {
			return err
		}
		if !work.spend(len(compiled.AllowedValues) + len(compiled.Default.Items) + 1) {
			return invalidCompiled()
		}
		output.arguments = append(output.arguments, compiled)
		output.ArgumentDefinitions = append(output.ArgumentDefinitions, definition)
	}
	return nil
}
func (state *compilerState) compileActionClasses(name string, output *participantAction) {
	source := fieldValue(state.input.model.ActionContracts)[name]
	for _, precondition := range fieldValue(source.Preconditions) {
		output.preconditions = append(output.preconditions, participantConditionDeclaration{ID: fieldValue(precondition.PreconditionId), Class: string(fieldValue(precondition.PreconditionClass)), SupportRefs: fieldValue(precondition.SupportRefs), EvidenceRefs: fieldValue(precondition.EvidenceRefs)})
		if class := string(fieldValue(precondition.PreconditionClass)); class != "" {
			output.PreconditionClasses = append(output.PreconditionClasses, class)
		}
	}
	for _, effect := range fieldValue(source.Effects) {
		output.effects = append(output.effects, participantEffectDeclaration{ID: fieldValue(effect.EffectId), Class: string(fieldValue(effect.EffectClass)), TargetRefs: fieldValue(effect.TargetRefs), EvidenceRefs: fieldValue(effect.EvidenceRefs)})
		if class := string(fieldValue(effect.EffectClass)); class != "" {
			output.EffectClasses = append(output.EffectClasses, class)
		}
	}
	for _, failure := range fieldValue(source.FailureClasses) {
		output.FailureClasses = append(output.FailureClasses, string(failure))
	}
	for _, mapping := range fieldValue(source.BackendFailureMappings) {
		output.BackendFailureMappings = append(output.BackendFailureMappings, participantFailureMapping{fieldValue(mapping.BackendErrorCode), string(fieldValue(mapping.FailureClass)), fieldValue(mapping.Diagnostic)})
	}
}
func (state *compilerState) compileActionInteractions(name string, output *participantAction) {
	source := fieldValue(state.input.model.ActionContracts)[name]
	for _, interaction := range fieldValue(source.Interactions) {
		if class := string(fieldValue(interaction.InteractionClass)); class != "" {
			output.InteractionClasses = append(output.InteractionClasses, class)
		}
		output.SharedStateRefs = append(output.SharedStateRefs, fieldValue(interaction.SharedStateRefs)...)
		if fieldValue(interaction.Commutative) {
			output.CommutativeInteractionTargets = append(output.CommutativeInteractionTargets, fieldValue(interaction.Target))
		}
		if raw := fieldValue(interaction.MergeRuleRef); len(raw) > 0 && string(raw) != termNull {
			output.MergeRuleRefs = append(output.MergeRuleRefs, rawString(raw))
		}
	}
}
func (state *compilerState) compileActionTiming(name string, output *participantAction) {
	source := fieldValue(state.input.model.ActionContracts)[name]
	for _, temporal := range fieldValue(source.TemporalContracts) {
		declaration := participantTemporalDeclaration{ID: fieldValue(temporal.TemporalId), Domain: string(fieldValue(temporal.TimeDomain)), Authority: fieldValue(temporal.ClockAuthority), EventPoints: []string{}, BackendDisclosureRefs: fieldValue(temporal.BackendDisclosureRefs), Reset: participantOptionalString(fieldValue(temporal.ResetBoundary)), Replay: participantOptionalString(fieldValue(temporal.ReplayBoundary))}
		for _, point := range fieldValue(temporal.EventPoints) {
			declaration.EventPoints = append(declaration.EventPoints, string(point))
		}
		output.temporal = append(output.temporal, declaration)
		if id := fieldValue(temporal.TemporalId); id != "" {
			output.TemporalContractIDs = append(output.TemporalContractIDs, id)
		}
		if kind := string(fieldValue(temporal.TemporalKind)); kind != "" {
			output.TemporalKinds = append(output.TemporalKinds, kind)
		}
		if domain := string(fieldValue(temporal.TimeDomain)); domain != "" {
			output.TimeDomains = append(output.TimeDomains, domain)
		}
		if authority := fieldValue(temporal.ClockAuthority); authority != "" {
			output.ClockAuthorities = append(output.ClockAuthorities, authority)
		}
	}
	for _, disclosure := range fieldValue(source.BackendTimingDisclosures) {
		output.BackendTimingDisclosures = append(output.BackendTimingDisclosures, participantTimingDisclosure{fieldValue(disclosure.DisclosureId), string(fieldValue(disclosure.DisclosureKind)), string(fieldValue(disclosure.SupportMode)), fieldValue(disclosure.Description), nonNilStrings(fieldValue(disclosure.AffectedTemporalIds)), nonNilStrings(fieldValue(disclosure.Limitations))})
	}
}
func (output *participantAction) uniqueTerms() {
	output.PreconditionClasses = dedupe(output.PreconditionClasses)
	output.EffectClasses = dedupe(output.EffectClasses)
	output.FailureClasses = dedupe(output.FailureClasses)
	output.InteractionClasses = dedupe(output.InteractionClasses)
	output.SharedStateRefs = dedupe(output.SharedStateRefs)
	output.CommutativeInteractionTargets = dedupe(output.CommutativeInteractionTargets)
	output.MergeRuleRefs = dedupe(output.MergeRuleRefs)
	output.TemporalContractIDs = dedupe(output.TemporalContractIDs)
	output.TemporalKinds = dedupe(output.TemporalKinds)
	output.TimeDomains = dedupe(output.TimeDomains)
	output.ClockAuthorities = dedupe(output.ClockAuthorities)
}
