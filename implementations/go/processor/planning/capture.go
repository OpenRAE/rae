package planning

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

type captureOffer struct {
	ID                  string   `json:"offer_id"`
	OutputContract      string   `json:"output_contract"`
	FieldSelectors      []string `json:"field_selectors"`
	ArtifactRoles       []string `json:"artifact_roles"`
	MediaTypes          []string `json:"media_types"`
	CaptureKind         string   `json:"capture_kind"`
	SourceClasses       []string `json:"source_classes"`
	SourceRefs          []string `json:"source_refs"`
	Scopes              []string `json:"scopes"`
	ScopeRefs           []string `json:"scope_refs"`
	ChannelKinds        []string `json:"channel_kinds"`
	ChannelRefs         []string `json:"channel_refs"`
	WindowKinds         []string `json:"window_kinds"`
	IntegrityModes      []string `json:"integrity_modes"`
	Sensitivity         string   `json:"sensitivity"`
	Availability        string   `json:"availability"`
	Fidelity            string   `json:"fidelity"`
	Disclosure          string   `json:"disclosure"`
	RetentionPolicyRefs []string `json:"retention_policy_refs"`
	ExportPolicy        string   `json:"export_policy"`
	RedactionPolicy     *string  `json:"redaction_policy"`
}
type captureOfferIndex struct {
	offer captureOffer
	sets  map[string]map[string]bool
}

func captureAdmission(model processor.CompiledScenario, component json.RawMessage) ([]diagnostic.Diagnostic, error) {
	var observation struct {
		Offers []captureOffer `json:"capture_offers"`
	}
	if len(component) > 0 && json.Unmarshal(component, &observation) != nil {
		return nil, invalidPlan()
	}
	return captureDiagnostics(model.CaptureDemands, observation.Offers)
}
func captureDiagnostics(demands []processor.CaptureDemand, offers []captureOffer) ([]diagnostic.Diagnostic, error) {
	result := []diagnostic.Diagnostic{}
	remaining := value.Plan().MaxOperations
	spend := func(count int) bool {
		if count > remaining {
			return false
		}
		remaining -= count
		return true
	}
	prepared, err := prepareCaptureOffers(offers, spend)
	if err != nil {
		return nil, err
	}
	ordered := slices.Clone(demands)
	slices.SortFunc(ordered, func(a, b processor.CaptureDemand) int {
		if order := strings.Compare(a.Address, b.Address); order != 0 {
			return order
		}
		return strings.Compare(a.DemandID, b.DemandID)
	})
	for _, demand := range ordered {
		failures, err := captureDemandFailures(demand, prepared, spend)
		if err != nil {
			return nil, err
		}
		for _, failure := range failures {
			result = append(result, planDiagnostic("capture."+failure, "capture", demand.Address, "Required capture '"+demand.DemandID+"' is not covered: "+strings.ReplaceAll(failure, "-", " ")+"."))
		}
	}
	return result, nil
}

func prepareCaptureOffers(offers []captureOffer, spend func(int) bool) ([]captureOfferIndex, error) {
	prepared := make([]captureOfferIndex, len(offers))
	for i, offer := range offers {
		index := captureOfferIndex{offer: offer, sets: map[string]map[string]bool{}}
		for _, field := range []struct {
			name   string
			values []string
		}{{"field_selectors", offer.FieldSelectors}, {"artifact_roles", offer.ArtifactRoles}, {"media_types", offer.MediaTypes}, {"source_classes", offer.SourceClasses}, {"source_refs", offer.SourceRefs}, {"scopes", offer.Scopes}, {"scope_refs", offer.ScopeRefs}, {"channel_kinds", offer.ChannelKinds}, {"channel_refs", offer.ChannelRefs}, {"window_kinds", offer.WindowKinds}, {"integrity_modes", offer.IntegrityModes}, {"retention_policy_refs", offer.RetentionPolicyRefs}} {
			if !spend(len(field.values)) {
				return nil, invalidPlan()
			}
			set := map[string]bool{}
			for _, entry := range field.values {
				set[entry] = true
			}
			index.sets[field.name] = set
		}
		prepared[i] = index
	}
	return prepared, nil
}

func captureDemandFailures(demand processor.CaptureDemand, prepared []captureOfferIndex, spend func(int) bool) ([]string, error) {
	var failures []string
	switch {
	case demand.CaptureSpecRef != "" || demand.CaptureRequirementRef != "":
		failures = []string{"reference-unresolved"}
	case len(prepared) == 0:
		failures = []string{"offer-missing"}
	default:
		return closestCaptureFailures(demand, prepared, spend)
	}
	return failures, nil
}

func closestCaptureFailures(demand processor.CaptureDemand, prepared []captureOfferIndex, spend func(int) bool) ([]string, error) {
	bestID := ""
	var best []string
	for _, index := range prepared {
		if !spend(20) {
			return nil, invalidPlan()
		}
		failed, err := index.failures(demand, spend)
		if err != nil {
			return nil, err
		}
		offer := index.offer
		if best == nil || len(failed) < len(best) || len(failed) == len(best) && (slices.Compare(failed, best) < 0 || slices.Equal(failed, best) && offer.ID < bestID) {
			best, bestID = failed, offer.ID
		}
		if len(best) == 0 {
			break
		}
	}
	return best, nil
}

func (index captureOfferIndex) failures(demand processor.CaptureDemand, spend func(int) bool) ([]string, error) {
	offer := index.offer
	failed := []string{}
	add := func(condition bool, failure string) {
		if condition {
			failed = append(failed, failure)
		}
	}
	add(demand.OutputContract != "" && demand.OutputContract != offer.OutputContract, "output-contract-mismatch")
	add(demand.CaptureKind != "" && demand.CaptureKind != offer.CaptureKind, "capture-kind-mismatch")
	add(demand.Sensitivity != "" && offer.Sensitivity != "*" && demand.Sensitivity != offer.Sensitivity, "sensitivity-mismatch")
	add(offer.Availability != "available", "availability-insufficient")
	add(offer.Fidelity != "complete", "fidelity-insufficient")
	add(demand.Disclosure != offer.Disclosure, "disclosure-insufficient")
	add(demand.ExportPolicy != "not-required" && demand.ExportPolicy != offer.ExportPolicy, "export-policy-mismatch")
	redactionEqual := demand.RedactionPolicy == nil && offer.RedactionPolicy == nil || demand.RedactionPolicy != nil && offer.RedactionPolicy != nil && *demand.RedactionPolicy == *offer.RedactionPolicy
	add(!redactionEqual, "redaction-policy-mismatch")
	for _, field := range []struct {
		name, failure, comparison string
		required                  []string
	}{
		{"field_selectors", "field-selector-missing", "pointers", demand.FieldSelectors}, {"artifact_roles", "artifact-role-mismatch", termSubset, demand.ArtifactRoles}, {"media_types", "media-type-mismatch", "overlap", demand.MediaTypes}, {"source_classes", "source-class-mismatch", termSubset, demand.SourceClasses}, {"source_refs", "source-ref-mismatch", termSubset, demand.SourceRefs}, {"scopes", "scope-mismatch", termSubset, demand.Scopes}, {"scope_refs", "scope-ref-mismatch", "exact-subset", demand.ScopeRefs}, {"channel_kinds", "channel-mismatch", termSubset, demand.ChannelKinds}, {"channel_refs", "channel-ref-mismatch", termSubset, demand.ChannelRefs}, {"window_kinds", "window-mismatch", termSubset, demand.WindowKinds}, {"integrity_modes", "integrity-mismatch", termSubset, demand.IntegrityModes}, {"retention_policy_refs", "retention-mismatch", termSubset, demand.RetentionPolicyRefs},
	} {
		if !spend(len(field.required)) {
			return nil, invalidPlan()
		}
		matches := captureDimensionSupported(field.required, index.sets[field.name], field.comparison)
		add(!matches, field.failure)
	}
	slices.Sort(failed)
	return failed, nil
}

func captureDimensionSupported(required []string, supported map[string]bool, comparison string) bool {
	if len(required) == 0 {
		return true
	}
	if comparison == "overlap" {
		for _, entry := range required {
			if supported[entry] {
				return true
			}
		}
		return false
	}
	wildcard := "*"
	if comparison == "pointers" {
		wildcard = ""
	}
	if comparison != "exact-subset" && supported[wildcard] {
		return true
	}
	for _, entry := range required {
		if !supported[entry] {
			return false
		}
	}
	return true
}
