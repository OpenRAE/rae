package analysis

import (
	"encoding/json"
	"maps"
	"slices"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
)

// analysisProfiles retains only immutable packaged authority.
//
//nolint:gochecknoglobals // Immutable packaged owner; no request state is shared.
var analysisProfiles = sync.OnceValues(func() (*profile.Profiles, error) {
	schemas, err := transportOwner()
	if err != nil {
		return nil, err
	}
	return profile.Load(schemas)
})

type opacityClaimContext struct{ claim, catalog []byte }

func (c opacityClaimContext) BehavioralCatalog() []byte { return slices.Clone(c.catalog) }
func (c opacityClaimContext) BehavioralClaim() []byte   { return slices.Clone(c.claim) }
func opacityOperational() error                         { return fault.New(fault.Operational, "opacity-profile-mismatch", nil) }
func loadOpacityProfile(input map[string]any) (map[string]any, error) {
	return loadOpacityProfileInCatalog(input, nil)
}
func loadOpacityProfileInCatalog(input map[string]any, catalog []byte) (map[string]any, error) {
	profiles, err := analysisProfiles()
	if err != nil {
		return nil, err
	}
	for _, candidate := range profiles.Documents() {
		if candidate.ContractID != termBehavioralRelationProfileV1 {
			continue
		}
		document, err := decodeObject(candidate.JSON, 8<<20)
		if err != nil {
			return nil, err
		}
		if document[termProfileID] == input[termProfileID] && document[termProfileRevision] == input[termProfileRevision] {
			return readmitOpacityProfile(input, candidate.JSON, catalog)
		}
	}
	return nil, invalidAnalysis()
}
func opacityProfileFor(input map[string]any, source *JSONInput) (map[string]any, error) {
	if source.Profile.ContractID() == "" {
		return loadOpacityProfileInCatalog(input, source.Catalog.JSON())
	}
	if source.Profile.ContractID() != termBehavioralRelationProfileV1 {
		return nil, invalidAnalysis()
	}
	return readmitOpacityProfile(input, source.Profile.JSON(), source.Catalog.JSON())
}
func readmitOpacityProfile(input map[string]any, raw, catalog []byte) (map[string]any, error) {
	owner, err := analysisOwner()
	if err != nil {
		return nil, err
	}
	transport, err := transportOwner()
	if err != nil {
		return nil, err
	}
	claim, err := canonical(input[termClaim])
	if err != nil {
		return nil, err
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	if _, err = owner.Validate(termBehavioralRelationProfileV1, raw, limits, opacityClaimContext{claim: claim, catalog: catalog}); err != nil {
		return nil, opacityOperational()
	}
	full, err := transport.Defaulted(termBehavioralRelationProfileV1, raw, limits)
	if err != nil {
		return nil, err
	}
	document := object(full)
	identity, err := hash(full)
	if err != nil {
		return nil, err
	}
	if identity != input[fieldProfileDigest] || document[termProfileID] != input[termProfileID] || document[termProfileRevision] != input[termProfileRevision] || object(document[termParameters])[termKind] != "participant-predicate-opacity/v1" {
		return nil, opacityOperational()
	}
	return document, nil
}
func integer(value any) int {
	number, ok := value.(json.Number)
	if !ok {
		return 0
	}
	n, _ := number.Int64()
	return int(n)
}
func stringValues(value any) []string {
	items := array(value)
	result := make([]string, 0, len(items))
	for _, item := range items {
		result = append(result, text(item))
	}
	return result
}
func rowStrings(points []opacityPoint, selectField func(opacityPoint) string) map[string]bool {
	result := map[string]bool{}
	for _, point := range points {
		result[selectField(point)] = true
	}
	return result
}
func opacityDomains(input, profile map[string]any, points []opacityPoint, model bool) error {
	parameters := object(profile[termParameters])
	if err := opacityCountBounds(input, parameters, model); err != nil {
		return err
	}
	checks := []struct {
		values      []string
		selectField func(opacityPoint) string
	}{
		{stringValues(parameters[termSchedulerRefs]), func(p opacityPoint) string { return p.Scheduler }},
		{stringValues(parameters[termEnvironmentRefs]), func(p opacityPoint) string { return p.Environment }},
		{stringValues(object(parameters[termOrder])[termOrderRefs]), func(p opacityPoint) string { return p.Order }},
		{[]string{text(object(parameters["horizon"])[termCutRef])}, func(p opacityPoint) string { return p.Cut }},
	}
	for _, check := range checks {
		if !maps.Equal(stringsSet(check.values), rowStrings(points, check.selectField)) {
			return opacityOperational()
		}
	}
	pairs := map[string]bool{}
	for _, scheduler := range checks[0].values {
		for _, environment := range checks[1].values {
			pairs[scheduler+"\x00"+environment] = true
		}
	}
	if !maps.Equal(pairs, rowStrings(points, func(p opacityPoint) string { return p.Scheduler + "\x00" + p.Environment })) {
		return opacityOperational()
	}
	strategies := rowStrings(points, func(p opacityPoint) string { return p.Strategy })
	strategy := object(parameters[termStrategy])
	if strategy[termKind] == "active" {
		if !maps.Equal(strategies, stringsSet(stringValues(strategy[termStrategyRefs]))) {
			return opacityOperational()
		}
	} else if len(strategies) != 1 {
		return opacityOperational()
	}
	coalition := object(parameters["observer"])[termKind] == "coalition"
	for _, point := range points {
		if (point.Coalition != nil) != coalition {
			return opacityOperational()
		}
	}
	return nil
}
func boundedOpacityConfiguration() map[string]any {
	return map[string]any{
		fieldProfile: "raes-participant-opacity-checker/v1", "tool_id": "raes-processor-participant-opacity", "tool_version": initialVersion, fieldAlgorithm: "exhaustive-information-cell-scan/v1", "information_cell_key": "initial-observation-memory-release-coalition-strategy-order/v1", "counterexample_selection": "lowest-canonical-ordinal/v1", "max_points": 4096,
	}
}
func normalizeOpacityRows(rows []any) []any {
	result := slices.Clone(rows)
	slices.SortFunc(result, func(a, b any) int { return integer(object(a)["ordinal"]) - integer(object(b)["ordinal"]) })
	return result
}
func opacityReason(document map[string]any, domain, profile, outcome, code, address, message string) {
	document[fieldOutcome] = outcome
	document[fieldDiagnostics] = []any{map[string]any{termDomain: domain, fieldCode: domain + "." + code, fieldAddress: address, termMessage: message, termSeverity: severityError}}
	document[outcomeUnsupported] = map[string]any{fieldProfile: profile, fieldReasonCodes: []string{domain + "." + code}}
}
func opacityResult(contract string, document map[string]any) (Result, error) {
	result, err := admitOutput(contract, document, nil)
	if err != nil {
		return result, err
	}
	for _, raw := range array(document[fieldDiagnostics]) {
		d := object(raw)
		result.Diagnostics = append(result.Diagnostics, diagnosticRecord(d))
	}
	return result, nil
}

func opacityCountBounds(input, parameters map[string]any, model bool) error {
	bounds := object(parameters["bounds"])
	counts := object(input[termDeclaredCounts])
	for _, field := range []string{termPoints, "runs", "cuts", "strategies", "scheduler_environment_pairs", "order_variants"} {
		name := field
		if model && name == termPoints {
			name = termStates
		}
		if integer(counts[name]) > integer(bounds["max_"+field]) {
			return opacityOperational()
		}
	}

	return nil
}
