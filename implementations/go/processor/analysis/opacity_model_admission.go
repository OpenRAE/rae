package analysis

import (
	"maps"
	"slices"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/contract/concept"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// analysisConcepts retains only immutable packaged authority.
//
//nolint:gochecknoglobals // Immutable packaged owner; no request state is shared.
var analysisConcepts = sync.OnceValues(func() (*concept.Authority, error) {
	schemas, err := transportOwner()
	if err != nil {
		return nil, err
	}
	return concept.Load(schemas)
})

func admitOpacityCatalog(input map[string]any, source *JSONInput) error {
	raw := source.Catalog.JSON()
	if source.Catalog.ContractID() == "" {
		var err error
		raw, err = packagedOpacityCatalog(text(object(input[termClaim])[termTaxonomyRevision]))
		if err != nil {
			return err
		}
	} else if source.Catalog.ContractID() != termBehavioralRelationsV1 {
		return invalidAnalysis()
	}
	document, err := admitOpacityDocument(&JSONInput{Data: raw}, termBehavioralRelationsV1, 8<<20)
	if err != nil {
		return err
	}
	identity, err := hash(document)
	if err != nil {
		return err
	}
	claim := object(input[termClaim])
	if identity != input["catalog_digest"] || document[termTaxonomyRevision] != claim[termTaxonomyRevision] || document[termTaxonomyID] != claim[termTaxonomyID] {
		return opacityOperational()
	}
	return nil
}
func packagedOpacityCatalog(revision string) ([]byte, error) {
	authority, err := analysisConcepts()
	if err != nil {
		return nil, err
	}
	for _, candidate := range authority.Documents() {
		if candidate.ContractID != termBehavioralRelationsV1 {
			continue
		}
		document, err := decodeObject(candidate.JSON, 8<<20)
		if err != nil {
			return nil, err
		}
		if document[termTaxonomyRevision] == revision {
			return candidate.JSON, nil
		}
	}
	return nil, invalidAnalysis()
}
func admitModelAssumptions(input, profile map[string]any, points []opacityPoint) error {
	parameters := object(profile[termParameters])
	assumptions := object(input[termAssumptions])
	strategy := object(parameters[termStrategy])
	strategies := assumptions[termStrategyRefs]
	if strategy[termKind] == "active" {
		strategies = strategy[termStrategyRefs]
	} else if len(array(strategies)) != 1 {
		return opacityOperational()
	}
	expected := map[string]any{"strategy_kind": strategy[termKind], termStrategyRefs: strategies, termSchedulerRefs: parameters[termSchedulerRefs], termEnvironmentRefs: parameters[termEnvironmentRefs], "order_treatment": object(parameters[termOrder])["treatment"], termOrderRefs: object(parameters[termOrder])[termOrderRefs], termCutRef: object(parameters["horizon"])[termCutRef], "nondeterminism": parameters["nondeterminism"], "time_model": object(parameters["time"])["model"], "progress": object(parameters["time"])["progress"], "probability": parameters["probability"]}
	actualDigest, err := hash(assumptions)
	if err != nil {
		return err
	}
	expectedDigest, err := hash(expected)
	if err != nil {
		return err
	}
	if actualDigest != expectedDigest {
		return opacityOperational()
	}
	if err = opacityDomains(input, profile, points, true); err != nil {
		return err
	}
	if !maps.Equal(stringsSet(stringValues(strategies)), rowStrings(points, func(point opacityPoint) string { return point.Strategy })) {
		return opacityOperational()
	}
	return admitInitialOpacityDomain(input, parameters, points, strategies)
}

func modelOpacityConfiguration() map[string]any {
	return map[string]any{
		fieldProfile: "raes-participant-opacity-explicit-state/v1", "tool_id": "raes-processor-participant-opacity-model-check", "tool_version": initialVersion, "package": "raes", "package_version": analysisPackageVersion, fieldAlgorithm: "complete-finite-transition-fixed-point/v1", "traversal": "breadth-first-canonical/v1", "opacity_kernel": "participant-opacity-information-cell-kernel/v1", "information_cell_key": "initial-observation-memory-release-coalition-strategy-order/v1", "counterexample_selection": "lowest-state-ordinal-canonical-shortest-path/v1", "max_states": 4096, "max_transitions": 65536,
	}
}
func opacityModelUnsupported(input map[string]any) []diagnostic.Diagnostic {
	findings := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		findings = append(findings, diagnostic.Diagnostic{Code: "participant-opacity-model-check." + code, Domain: opacityModelKind, Address: address, Message: message, Severity: severityError})
	}
	if input["complete_model"] != true {
		add("incomplete-model", "/complete_model", "The transition artifact is not declared to be the complete finite model.")
	}
	counts := object(input[termDeclaredCounts])
	assumptions := object(input[termAssumptions])
	if integer(counts[termStates]) > 4096 || integer(counts["transitions"]) > 65536 {
		add("bound-exceeded", "/declared_counts", "The complete finite model exceeds the deterministic checker resource profile.")
	}
	if len(array(assumptions[termSchedulerRefs])) != 1 || len(array(assumptions[termEnvironmentRefs])) != 1 {
		add("unsupported-scheduler-quantification", "/assumptions", "The v1 checker supports only the profile's unambiguous singleton scheduler/environment posture.")
	}
	if assumptions["order_treatment"] != "total-order" {
		add("unsupported-order-treatment", "/assumptions/order_treatment", "The v1 checker supports exact total-order models only.")
	}
	slices.SortFunc(findings, func(a, b diagnostic.Diagnostic) int {
		if a.Address < b.Address || a.Address == b.Address && a.Code < b.Code {
			return -1
		}
		if a.Address == b.Address && a.Code == b.Code {
			return 0
		}
		return 1
	})
	return findings
}

func admitInitialOpacityDomain(input, parameters map[string]any, points []opacityPoint, strategies any) error {
	initial := map[[4]string]bool{}
	for _, value := range array(input["initial_state_ordinals"]) {
		point := points[integer(value)]
		initial[[4]string{point.Strategy, point.Scheduler, point.Environment, point.Order}] = true
	}
	expectedSize := len(stringValues(strategies)) * len(stringValues(parameters[termSchedulerRefs])) * len(stringValues(parameters[termEnvironmentRefs])) * len(stringValues(object(parameters[termOrder])[termOrderRefs]))
	if len(initial) != expectedSize {
		return opacityOperational()
	}

	return nil
}
