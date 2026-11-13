package processor

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

type participantOutcomeSourceDeclaration struct {
	ID, Layer, Ref               string
	EvidenceRefs, ProvenanceRefs []string
}
type participantOutcomeTargetDeclaration struct {
	ID, Layer, Ref            string
	EvidenceRefs, Limitations []string
	Governance                *string
}
type participantOutcomeSourceRecord struct {
	ID             string   `json:"source_id"`
	Layer          string   `json:"source_layer"`
	Ref            string   `json:"ref"`
	Observed       string   `json:"observed_value"`
	EvidenceRefs   []string `json:"evidence_refs"`
	ProvenanceRefs []string `json:"provenance_refs"`
	Diagnostics    []string `json:"diagnostics"`
}
type participantOutcomeTargetRecord struct {
	ID           string   `json:"target_id"`
	Layer        string   `json:"target_layer"`
	Ref          string   `json:"ref"`
	Interpreted  string   `json:"interpreted_value"`
	EvidenceRefs []string `json:"evidence_refs"`
	Limitations  []string `json:"limitations"`
	Governance   *string  `json:"governance_ref"`
	Diagnostics  []string `json:"diagnostics"`
}
type participantOutcomeRecord struct {
	ID           string                           `json:"interpretation_id"`
	Rule         string                           `json:"rule_address"`
	Participant  string                           `json:"participant_address"`
	Episode      string                           `json:"episode_id"`
	Point        string                           `json:"observation_point"`
	Sources      []participantOutcomeSourceRecord `json:"source_bindings"`
	Targets      []participantOutcomeTargetRecord `json:"target_bindings"`
	EvidenceRefs []string                         `json:"evidence_refs"`
	Limitations  []string                         `json:"limitations"`
	Diagnostics  []string                         `json:"diagnostics"`
}

func participantOptionalString(raw json.RawMessage) *string {
	if len(raw) == 0 || string(raw) == termNull {
		return nil
	}
	text := rawString(raw)
	return &text
}
func participantOptionalEqual(left, right *string) bool {
	return left == nil && right == nil || left != nil && right != nil && *left == *right
}
func participantOptionalRepr(value *string) string {
	if value == nil {
		return termPythonNone
	}
	return pyrepr.Quote(*value)
}
func participantProvenanceRequired(layer string) bool {
	return slices.Contains([]string{"participant_episode_status", "benchmark_milestone", "subtask", "gold_step", "human_assistance", "scaffold_variant", "cost_resource_telemetry", "privacy_redaction_result"}, layer)
}
func (record participantOutcomeRecord) locallyValid() bool {
	if record.ID == "" || !strings.HasPrefix(record.Rule, "participant.outcome-interpretation-rule.") || record.Participant == "" || record.Episode == "" || record.Point == "" || len(record.Sources) == 0 || len(record.Targets) == 0 || len(record.EvidenceRefs) == 0 || len(record.Limitations) == 0 {
		return false
	}
	if !participantUniqueStrings(record.EvidenceRefs) || !participantUniqueStrings(record.Limitations) || !participantUniqueStrings(record.Diagnostics) {
		return false
	}
	return record.sourcesValid() && record.targetsValid()
}
func (record participantOutcomeRecord) sourcesValid() bool {
	ids := map[string]bool{}
	for _, source := range record.Sources {
		if source.ID == "" || ids[source.ID] || source.Ref == "" || source.Observed == "" || !participantUniqueStrings(source.EvidenceRefs) || !participantUniqueStrings(source.ProvenanceRefs) || !participantUniqueStrings(source.Diagnostics) {
			return false
		}
		ids[source.ID] = true
	}
	return true
}
func (record participantOutcomeRecord) targetsValid() bool {
	ids := map[string]bool{}
	for _, target := range record.Targets {
		if target.ID == "" || ids[target.ID] || target.Ref == "" || target.Interpreted == "" || len(target.EvidenceRefs) == 0 || len(target.Limitations) == 0 || !participantUniqueStrings(target.EvidenceRefs) || !participantUniqueStrings(target.Limitations) || !participantUniqueStrings(target.Diagnostics) {
			return false
		}
		ids[target.ID] = true
		if target.Governance != nil && *target.Governance == "" || target.Layer == "reward_signal" && target.Governance == nil {
			return false
		}
	}
	return true
}
func (record participantOutcomeRecord) sourceViolations(rule participantOutcomeRule, address string, violations *participantViolations) {
	if !violations.spend(len(rule.sources) + len(record.Sources)) {
		return
	}
	declared := map[participantDeclarationKey]participantOutcomeSourceDeclaration{}
	for _, item := range rule.sources {
		declared[participantDeclarationKey{item.ID, item.Layer}] = item
	}
	reported := map[participantDeclarationKey]bool{}
	for _, source := range record.Sources {
		key := participantDeclarationKey{source.ID, source.Layer}
		reported[key] = true
		definition, present := declared[key]
		if !present {
			violations.add(fmt.Sprintf("outcome interpretation %s source %s is not declared by %s", pyrepr.Quote(record.ID), pyrepr.Quote(source.ID), address))
			continue
		}
		prefix := fmt.Sprintf("outcome interpretation %s source %s", pyrepr.Quote(record.ID), pyrepr.Quote(source.ID))
		if source.Ref != definition.Ref {
			violations.add(fmt.Sprintf("%s ref %s does not match declared ref %s", prefix, pyrepr.Quote(source.Ref), pyrepr.Quote(definition.Ref)))
		}
		for _, ref := range violations.difference(source.EvidenceRefs, definition.EvidenceRefs) {
			violations.add(fmt.Sprintf("%s reports undeclared evidence_ref %s", prefix, pyrepr.Quote(ref)))
		}
		for _, ref := range violations.difference(source.ProvenanceRefs, definition.ProvenanceRefs) {
			violations.add(fmt.Sprintf("%s reports undeclared provenance_ref %s", prefix, pyrepr.Quote(ref)))
		}
		for _, ref := range violations.difference(definition.ProvenanceRefs, source.ProvenanceRefs) {
			violations.add(fmt.Sprintf("%s omits declared provenance_ref %s", prefix, pyrepr.Quote(ref)))
		}
	}
	record.unreportedSourceViolations(declared, reported, violations)
}
func (record participantOutcomeRecord) unreportedSourceViolations(declared map[participantDeclarationKey]participantOutcomeSourceDeclaration, reported map[participantDeclarationKey]bool, violations *participantViolations) {
	keys := []participantDeclarationKey{}
	for key := range declared {
		keys = append(keys, key)
	}
	slices.SortFunc(keys, func(a, b participantDeclarationKey) int {
		if a.id != b.id {
			return strings.Compare(a.id, b.id)
		}
		return strings.Compare(a.class, b.class)
	})
	for _, key := range keys {
		if participantProvenanceRequired(key.class) && !reported[key] {
			violations.add(fmt.Sprintf("outcome interpretation %s source %s with provenance-required layer %s is not reported", pyrepr.Quote(record.ID), pyrepr.Quote(key.id), pyrepr.Quote(key.class)))
		}
	}
}
func (record participantOutcomeRecord) targetViolations(rule participantOutcomeRule, address string, violations *participantViolations) {
	if !violations.spend(len(rule.targets) + len(record.Targets)) {
		return
	}
	declared := map[participantDeclarationKey]participantOutcomeTargetDeclaration{}
	for _, item := range rule.targets {
		declared[participantDeclarationKey{item.ID, item.Layer}] = item
	}
	for _, target := range record.Targets {
		definition, present := declared[participantDeclarationKey{target.ID, target.Layer}]
		if !present {
			violations.add(fmt.Sprintf("outcome interpretation %s target %s is not declared by %s", pyrepr.Quote(record.ID), pyrepr.Quote(target.ID), address))
			continue
		}
		prefix := fmt.Sprintf("outcome interpretation %s target %s", pyrepr.Quote(record.ID), pyrepr.Quote(target.ID))
		if target.Ref != definition.Ref {
			violations.add(fmt.Sprintf("%s ref %s does not match declared ref %s", prefix, pyrepr.Quote(target.Ref), pyrepr.Quote(definition.Ref)))
		}
		if !participantOptionalEqual(target.Governance, definition.Governance) {
			violations.add(fmt.Sprintf("%s governance_ref %s does not match declared governance_ref %s", prefix, participantOptionalRepr(target.Governance), participantOptionalRepr(definition.Governance)))
		}
		for _, ref := range violations.difference(target.EvidenceRefs, definition.EvidenceRefs) {
			violations.add(fmt.Sprintf("%s reports undeclared evidence_ref %s", prefix, pyrepr.Quote(ref)))
		}
		if len(definition.Limitations) > 0 && len(violations.difference(target.Limitations, definition.Limitations)) > 0 {
			violations.add(prefix + " reports limitations outside the declared rule")
		}
	}
}
func (record participantOutcomeRecord) contractViolations(rule participantOutcomeRule, address string, violations *participantViolations) {
	record.sourceViolations(rule, address, violations)
	record.targetViolations(rule, address, violations)
	for _, ref := range violations.difference(record.EvidenceRefs, rule.EvidenceRefs) {
		violations.add(fmt.Sprintf("outcome interpretation %s reports undeclared evidence_ref %s", pyrepr.Quote(record.ID), pyrepr.Quote(ref)))
	}
}

// ParticipantOutcomeInterpretationViolations compares one local interpretation with its compiled rule.
func ParticipantOutcomeInterpretationViolations(model RuntimeModel, ruleAddress string, record admission.Fragment) ([]diagnostic.Diagnostic, error) {
	owned, err := nativeRuntimeModel(model)
	if err != nil {
		return nil, err
	}
	rule, ok := owned.participants.outcomes[ruleAddress]
	if !ok {
		return nil, participantContractInput()
	}
	var typed participantOutcomeRecord
	if err := participantFragmentDecode(record, admission.ParticipantOutcomeInterpretationRecord, &typed); err != nil {
		return nil, err
	}
	if !typed.locallyValid() {
		return nil, participantContractInput()
	}
	violations := newParticipantViolations()
	typed.contractViolations(rule, ruleAddress, violations)
	if violations.err != nil {
		return nil, violations.err
	}
	return participantFindings("participant.outcome-interpretation-rule-violation", ruleAddress, violations.messages), nil
}
