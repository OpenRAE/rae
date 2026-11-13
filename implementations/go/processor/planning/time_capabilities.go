package planning

import (
	"encoding/json"
	"math/big"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

type timeCapabilities struct {
	DomainKinds                   []string     `json:"supported_domain_kinds"`
	AuthorityKinds                []string     `json:"supported_authority_kinds"`
	AdvancementModes              []string     `json:"supported_advancement_modes"`
	SynchronizationModes          []string     `json:"supported_synchronization_modes"`
	MappingKinds                  []string     `json:"supported_mapping_kinds"`
	ConstraintKinds               []string     `json:"supported_constraint_kinds"`
	ResetBehaviors                []string     `json:"supported_reset_behaviors"`
	ReplayBehaviors               []string     `json:"supported_replay_behaviors"`
	MaxDomains                    *json.Number `json:"max_time_domains"`
	MaxClocks                     *json.Number `json:"max_clocks"`
	SupportsPause                 bool         `json:"supports_pause"`
	SupportsJump                  bool         `json:"supports_jump"`
	SupportsExactRationalMappings bool         `json:"supports_exact_rational_mappings"`
	SupportsAppendOnlyHistory     bool         `json:"supports_append_only_history"`
	SupportsRunProvenance         bool         `json:"supports_run_provenance"`
}

func timeDiagnostics(model processor.CompiledScenario, raw json.RawMessage) ([]diagnostic.Diagnostic, error) {
	result := []diagnostic.Diagnostic{}
	if !model.HasTimeModel {
		return result, nil
	}
	add := func(message string) {
		result = append(result, planDiagnostic("time.unsupported-capability", "time", "time.model", message))
	}
	if len(raw) == 0 || string(raw) == termNull {
		add("backend does not declare time capabilities")
		return result, nil
	}
	var caps timeCapabilities
	if json.Unmarshal(raw, &caps) != nil {
		return nil, invalidPlan()
	}
	domains, authorities, advancements, synchronizations, mappings, constraints, resets, replays := []string{}, []string{}, []string{}, []string{}, []string{}, []string{}, []string{}, []string{}
	pause, jump := false, false
	for _, domain := range model.TimeModel.Domains {
		domains = append(domains, domain.Kind)
	}
	for _, clock := range model.TimeModel.Clocks {
		authorities = append(authorities, clock.AuthorityKind)
		pause = pause || clock.SupportsPause
		jump = jump || clock.SupportsJump
	}
	for _, policy := range model.TimeModel.ProgressionPolicies {
		advancements = append(advancements, policy.AdvancementMode)
		synchronizations = append(synchronizations, policy.SynchronizationMode)
		resets = append(resets, policy.ResetBehavior)
		replays = append(replays, policy.ReplayBehavior)
	}
	for _, mapping := range model.TimeModel.Mappings {
		mappings = append(mappings, mapping.Kind)
	}
	for _, constraint := range model.TimeModel.Constraints {
		constraints = append(constraints, constraint.Kind)
	}
	gaps, err := timeCapabilityGaps(model, caps, domains, authorities, advancements, synchronizations, mappings, constraints, resets, replays, pause, jump)
	if err != nil {
		return nil, err
	}
	for _, gap := range gaps {
		add(gap)
	}
	return result, nil
}
func timeCapabilityGaps(model processor.CompiledScenario, caps timeCapabilities, domains, authorities, advancements, synchronizations, mappings, constraints, resets, replays []string, pause, jump bool) ([]string, error) {
	result := []string{}
	add := func(message string) { result = append(result, message) }
	for _, item := range []struct {
		label               string
		required, supported []string
	}{
		{"domain kinds", domains, caps.DomainKinds}, {"authority kinds", authorities, caps.AuthorityKinds}, {"advancement modes", advancements, caps.AdvancementModes}, {"synchronization modes", synchronizations, caps.SynchronizationModes}, {"mapping kinds", mappings, caps.MappingKinds}, {"constraint kinds", constraints, caps.ConstraintKinds}, {"reset behaviors", resets, caps.ResetBehaviors}, {"replay behaviors", replays, caps.ReplayBehaviors},
	} {
		if missing := missingTimeValues(item.required, item.supported); len(missing) > 0 {
			add("unsupported time " + item.label + ": " + strings.Join(missing, ", "))
		}
	}
	for _, item := range []struct {
		label    string
		required int
		maximum  *json.Number
	}{{"domains", len(model.TimeModel.Domains), caps.MaxDomains}, {"clocks", len(model.TimeModel.Clocks), caps.MaxClocks}} {
		if item.maximum == nil {
			continue
		}
		maximum, ok := capabilityInteger(*item.maximum)
		if !ok {
			return nil, invalidPlan()
		}
		if big.NewInt(int64(item.required)).Cmp(maximum) > 0 {
			add("time model requires " + strconv.Itoa(item.required) + " " + item.label + "; backend limit is " + maximum.String())
		}
	}
	for _, item := range []struct {
		required, supported bool
		label               string
	}{{pause, caps.SupportsPause, "pause control"}, {jump, caps.SupportsJump, "jump control"}, {len(model.TimeModel.Mappings) > 0, caps.SupportsExactRationalMappings, "exact rational mappings"}, {true, caps.SupportsAppendOnlyHistory, "append-only clock transition history"}, {true, caps.SupportsRunProvenance, "realized run provenance"}} {
		if item.required && !item.supported {
			add("time model requires " + item.label)
		}
	}
	return result, nil
}

func missingTimeValues(required, supported []string) []string {
	missing := []string{}
	for _, value := range required {
		if !slices.Contains(supported, value) {
			missing = append(missing, value)
		}
	}
	slices.Sort(missing)
	return slices.Compact(missing)
}
