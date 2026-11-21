package admission

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// ObservationFieldSelector selects a concern within a semantic scope.
type ObservationFieldSelector struct {
	Scope      string   `json:"semantic_scope"`
	Excluded   []string `json:"excluded_scopes"`
	Components []string `json:"component_refs"`
	Kind       string   `json:"data_kind"`
	Names      []string `json:"names"`
}

// ObservationDemandSelection carries the effective policy needed for field selection.
type ObservationDemandSelection struct {
	Scope      string                     `json:"scope"`
	Purpose    string                     `json:"purpose"`
	Mode       string                     `json:"mode"`
	Collection string                     `json:"collection"`
	Retention  string                     `json:"retention"`
	Export     string                     `json:"export"`
	Selectors  []ObservationFieldSelector `json:"selectors"`
}

// SelectObservationDemand applies effective policy without authorizing collection.
// A narrower scope suppresses inherited policy only for the same purpose.
func SelectObservationDemand(demands []ObservationDemandSelection, scope, address, kind, stage string) (bool, error) {
	if !slices.Contains([]string{termCollection, termRetention, termExport}, stage) {
		return false, fragmentInvalid()
	}
	if observationSelectionBounds(demands, scope, address, kind) != nil {
		return false, fragmentInvalid()
	}

	scope = strings.TrimPrefix(scope, "#")
	depths := map[string]int{}
	for _, demand := range demands {
		if observationContains(demand.Scope, scope) {
			depths[demand.Purpose] = max(depths[demand.Purpose], observationDepth(demand.Scope))
		}
	}
	for _, demand := range demands {
		if !observationContains(demand.Scope, scope) || observationDepth(demand.Scope) != depths[demand.Purpose] || !observationStageSelected(demand, stage) {
			continue
		}
		for _, selector := range demand.Selectors {
			if observationFieldSelected(selector, scope, address, kind) {
				return true, nil
			}
		}
	}
	return false, nil
}

func observationStageSelected(demand ObservationDemandSelection, stage string) bool {
	if demand.Purpose == termRealizationDescription || demand.Purpose == "operational" && stage != termCollection || !slices.Contains([]string{termSelected, termExhaustive, termOperationalOnly}, demand.Mode) {
		return false
	}
	decision := demand.Collection
	if stage == termRetention {
		decision = demand.Retention
	}
	if stage == termExport {
		decision = demand.Export
	}
	return decision == termRequire
}

func observationFieldSelected(selector ObservationFieldSelector, scope, address, kind string) bool {
	if !observationContains(selector.Scope, scope) || selector.Kind != "field" || !slices.Contains(selector.Names, kind) || len(selector.Components) > 0 && !slices.Contains(selector.Components, address) {
		return false
	}
	for _, excluded := range selector.Excluded {
		if observationContains(excluded, scope) {
			return false
		}
	}
	return true
}

func observationSelectionBounds(demands []ObservationDemandSelection, scope, address, kind string) error {
	if len(demands) > value.Runtime().MaxMembers {
		return fragmentInvalid()
	}
	values := make([]any, len(demands))
	for i, demand := range demands {
		if len(demand.Selectors) > value.Runtime().MaxMembers {
			return fragmentInvalid()
		}
		selectors := make([]any, len(demand.Selectors))
		for j, selector := range demand.Selectors {
			selectors[j] = []any{selector.Scope, selector.Excluded, selector.Components, selector.Kind, selector.Names}
		}
		values[i] = []any{demand.Scope, demand.Purpose, demand.Mode, demand.Collection, demand.Retention, demand.Export, selectors}
	}
	if CheckTransportTree([]any{scope, address, kind, values}, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return fragmentInvalid()
	}
	return nil
}
