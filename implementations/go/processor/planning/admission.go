package planning

import (
	"encoding/json"
	"sync"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

var planOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Immutable packaged validator; no request data is cached.

func checkTransport(contract string, document any) error {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if err := admission.CheckTransport(document, limits); err != nil {
		return err
	}
	owner, err := planOwner()
	if err != nil {
		return err
	}
	raw, err := json.Marshal(document)
	if err != nil {
		return invalidPlan()
	}
	return owner.CheckPortable(contract, raw, limits)
}

func prepareOptions(model processor.RuntimeModel, options Options) (PlanningContext, error) {
	for _, input := range []struct {
		contract string
		document any
		present  bool
	}{
		{"realization-envelope-v1", options.RealizationEnvelope, options.RealizationEnvelope != nil},
		{"runtime-snapshot-v1", options.Snapshot, options.Snapshot != nil},
		{"domain-profile-resolution-context-v1", options.ProfileContext, options.ProfileContext != nil},
		{"processor-manifest-v2", options.ProcessorManifest, options.ProcessorManifest != nil},
	} {
		if input.present {
			if err := checkTransport(input.contract, input.document); err != nil {
				return PlanningContext{}, err
			}
		}
	}
	if options.MixedControlAdmission != nil {
		admission, ok := options.MixedControlAdmission.(*mixedControlAdmission)
		if !ok || admission == nil || admission.model != model {
			return PlanningContext{}, invalidPlan()
		}
	}
	if err := checkNativeOptions(options); err != nil {
		return PlanningContext{}, err
	}
	var snapshot binding.RuntimeSnapshotV1
	if options.Snapshot == nil {
		if json.Unmarshal([]byte(`{"schema_version":"runtime-snapshot/v1","entries":{}}`), &snapshot) != nil {
			return PlanningContext{}, invalidPlan()
		}
	} else {
		snapshot = copyTransport(*options.Snapshot)
	}
	return PlanningContext{OriginalModel: model, Snapshot: snapshot, Scope: copyScope(options.Scope), ApparatusDecisions: map[RequirementKey]Closure{}, ArtifactAvailability: copyAvailability(options.ArtifactAvailability), ProfileContext: copyTransport(options.ProfileContext), MixedControlAdmission: options.MixedControlAdmission, RefreshEvaluation: options.RefreshEvaluation, ProcessorManifest: copyTransport(options.ProcessorManifest), RealizationEnvelope: copyTransport(options.RealizationEnvelope)}, nil
}

type optionTextBudget struct{ bytes, nodes int }

func (b *optionTextBudget) check(text string) bool {
	b.nodes++
	if len(text) > 1<<20 || b.nodes > 65536 || len(text) > (8<<20)-b.bytes {
		return false
	}
	b.bytes += len(text)
	return utf8.ValidString(text)
}
func (b *optionTextBudget) availability(entry ArtifactAvailability) bool {
	if !b.check(entry.Address) {
		return false
	}
	for _, values := range [][]string{entry.AvailableArtifactDigests, entry.AvailableCandidateIDs, entry.VerifiedLockedInputIDs, entry.SatisfiedConstraintIDs, entry.AvailableMaterializationSpecificationDigests, entry.VerifiedIntegrityRefs, entry.VerifiedAuthenticityRefs, entry.VerifiedAdmissionRefs, entry.VerifiedProvenanceRefs, entry.VerifiedEvidenceRefs} {
		if len(values) > 16384 {
			return false
		}
		for _, text := range values {
			if !b.check(text) {
				return false
			}
		}
	}
	return true
}
func checkNativeOptions(options Options) error {
	budget := optionTextBudget{}
	if options.Scope != nil {
		for _, text := range []*string{options.Scope.TargetName, options.Scope.RunID, options.Scope.InstantiationID} {
			if text != nil && !budget.check(*text) {
				return invalidPlan()
			}
		}
	}
	if len(options.ArtifactAvailability) > 16384 {
		return invalidPlan()
	}
	for _, entry := range options.ArtifactAvailability {
		if !budget.availability(entry) {
			return invalidPlan()
		}
	}
	return nil
}
