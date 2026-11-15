package admission

import (
	"io"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// ExperimentEvidenceInputs contains acquired bytes and their concrete authorities.
// Artifact locators are inert labels; this boundary never opens or fetches them.
type ExperimentEvidenceInputs struct {
	CaptureSpecs, EvidenceRecords map[string]validation.Value
	ArtifactReaders               map[string]io.Reader
	Scenarios                     []EvidenceScenario
}
type evidenceRequirement struct{ spec, requirement any }
type evidenceBinding struct{ requirement, version, artifactID, digest, locator string }
type experimentEvidence struct {
	owner        *Validator
	task, run    any
	requirements map[string]evidenceRequirement
	records      map[string][]any
	readers      map[string]io.Reader
	content      map[string]*experimentEvidencePayload
}

// ValidateExperimentRun checks task protocol, provenance and content-backed evidence.
// Successful cleanup or a metadata-only record cannot satisfy an evidence claim.
func ValidateExperimentRun(v *Validator, task, run validation.Value, inputs *ExperimentEvidenceInputs) error {
	taskView, err := v.experimentValue(task, termExperimentTaskV1)
	if err != nil {
		return err
	}
	runView, err := v.experimentValue(run, termExperimentRunV1)
	if err != nil {
		return err
	}
	if err = v.taskRunJoin(taskView, runView); err != nil {
		return err
	}
	relations := append(slices.Clone(array(at(taskView, "evidence_requirement_relations"))), array(at(runView, "evidence_requirement_relations"))...)
	if len(relations) > 0 {
		if inputs == nil {
			return invalid()
		}
		if err = v.experimentEvidenceRelations(relations, *inputs); err != nil {
			return err
		}
	}
	if inputs == nil {
		if taskClaimsEvidence(taskView) {
			return invalid()
		}
		return nil
	}
	state, err := v.prepareExperimentEvidence(taskView, runView, *inputs)
	if err != nil {
		return err
	}
	return state.validate()
}
func taskClaimsEvidence(task any) bool {
	if len(array(at(task, "evaluation_protocol", "observation_requirements"))) > 0 {
		return true
	}
	for _, metric := range object(at(task, "evaluation_protocol", "metric_definitions")) {
		if len(array(at(metric, "evidence_requirements"))) > 0 {
			return true
		}
	}
	return false
}
func (e *Validator) experimentEvidenceRelations(relations []any, inputs ExperimentEvidenceInputs) error {
	fragments := make([]Fragment, 0, len(relations))
	for _, relation := range relations {
		fragment, err := AdmitFragment(e, ExperimentEvidenceRequirementRelation, relation, experimentEvidenceLimits())
		if err != nil {
			return err
		}
		fragments = append(fragments, fragment)
	}
	specs := make([]binding.ExperimentCaptureSpecV1, 0, len(inputs.CaptureSpecs))
	for _, value := range inputs.CaptureSpecs {
		if value.ContractID() != contractExperimentCapture {
			return invalid()
		}
		transport, err := value.Transport()
		if err != nil {
			return err
		}
		spec, ok := transport.(binding.ExperimentCaptureSpecV1)
		if !ok {
			return invalid()
		}
		specs = append(specs, spec)
	}
	return CheckEvidenceRequirementRelations(e, fragments, slices.Clone(inputs.Scenarios), specs)
}
func (e *Validator) prepareExperimentEvidence(task, run any, inputs ExperimentEvidenceInputs) (*experimentEvidence, error) {
	if len(inputs.CaptureSpecs) > 1024 || len(inputs.EvidenceRecords) > 1024 || len(inputs.ArtifactReaders) > 1024 || len(array(at(run, "evidence_artifacts"))) > 1024 {
		return nil, invalid()
	}
	if err := evidenceArtifactBounds(run); err != nil {
		return nil, err
	}
	state := &experimentEvidence{owner: e, task: task, run: run, requirements: map[string]evidenceRequirement{}, records: map[string][]any{}, readers: maps.Clone(inputs.ArtifactReaders), content: map[string]*experimentEvidencePayload{}}
	specs, err := state.loadCaptureSpecs(inputs.CaptureSpecs)
	if err != nil {
		return nil, err
	}
	records, err := state.loadEvidenceRecords(inputs.EvidenceRecords)
	if err != nil {
		return nil, err
	}
	if !evidenceSuppliedSet(at(run, "traceability", "capture_spec_refs"), specs, "capture_spec_id", "spec_version") || !evidenceSuppliedSet(at(run, "traceability", "evidence_record_refs"), records, "evidence_record_id", "record_version") {
		return nil, invalid()
	}
	if err := evidenceAugmentationProducers(run); err != nil {
		return nil, err
	}
	return state, nil
}
func (s *experimentEvidence) loadCaptureSpecs(inputs map[string]validation.Value) ([]any, error) {
	specs := []any{}
	for _, id := range slices.Sorted(maps.Keys(inputs)) {
		spec, err := s.owner.experimentValue(inputs[id], contractExperimentCapture)
		if err != nil {
			return nil, err
		}
		specs = append(specs, spec)
		for id, requirement := range object(at(spec, "capture_requirements")) {
			if _, present := s.requirements[id]; present {
				return nil, invalid()
			}
			s.requirements[id] = evidenceRequirement{spec, requirement}
			if len(s.requirements) > 1024 {
				return nil, invalid()
			}
		}
	}
	return specs, nil
}
func (s *experimentEvidence) loadEvidenceRecords(inputs map[string]validation.Value) ([]any, error) {
	records := []any{}
	for _, id := range slices.Sorted(maps.Keys(inputs)) {
		record, err := s.owner.experimentValue(inputs[id], termExperimentEvidenceRecordV1)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
		key := join(stringAt(record, "capture_spec_ref", fieldRefID), stringAt(record, "capture_requirement_ref"))
		s.records[key] = append(s.records[key], record)
		requirement, present := s.requirements[stringAt(record, "capture_requirement_ref")]
		if !present || stringAt(requirement.spec, "capture_spec_id") != stringAt(record, "capture_spec_ref", fieldRefID) {
			return nil, invalid()
		}
	}
	return records, nil
}

func evidenceSuppliedSet(refs any, values []any, idField, versionField string) bool {
	referenced := rowTupleSet(refs, fieldRefID, fieldRefVersion)
	supplied := rowTupleSet(values, idField, versionField)
	return equalSet(referenced, supplied)
}
func evidenceArtifactBounds(run any) error {
	remaining := int64(256 << 20)
	for _, artifact := range array(at(run, "evidence_artifacts")) {
		size, ok := number(at(artifact, "size_bytes"))
		if !ok || !size.IsInt() || !size.Num().IsInt64() || size.Sign() < 0 || size.Num().Int64() > remaining {
			return invalid()
		}
		remaining -= size.Num().Int64()
	}
	return nil
}
func evidenceAugmentationProducers(run any) error {
	for _, disclosure := range array(at(run, "augmentation_disclosures")) {
		producer := at(disclosure, "augmented_by_ref")
		found := false
		for _, component := range object(at(run, "apparatus_context", termComponents)) {
			if stringAt(component, "component_kind") == stringAt(producer, fieldRefKind) && identityMatches(at(component, termIdentity), producer) {
				found = true
				break
			}
		}
		if !found {
			return invalid()
		}
	}
	return nil
}
func (s *experimentEvidence) validate() error {
	bindings := map[string]evidenceBinding{}
	for _, id := range slices.Sorted(maps.Keys(s.requirements)) {
		requirement := s.requirements[id]
		records := s.records[join(stringAt(requirement.spec, "capture_spec_id"), id)]
		if len(records) != 1 {
			return invalid()
		}
		record := records[0]
		if err := evidenceRecordBinding(s.task, s.run, requirement, record); err != nil {
			return err
		}
		artifact, err := evidenceArtifact(s.run, record)
		if err != nil {
			return err
		}
		if err = s.validateContent(requirement.requirement, record, artifact); err != nil {
			return err
		}
		bindings[id] = evidenceBinding{id, stringAt(record, "record_version"), stringAt(artifact, termArtifactID), stringAt(artifact, "checksum", "algorithm") + ":" + stringAt(artifact, "checksum", termValue), stringAt(artifact, "uri")}
	}
	return evidenceTaskBindings(s.task, s.run, bindings)
}
func evidenceTaskBindings(task, run any, bindings map[string]evidenceBinding) error {
	for _, requirement := range array(at(task, "evaluation_protocol", "observation_requirements")) {
		if !evidenceBindingMatches(bindings[stringAt(requirement, fieldRefID)], requirement, nil) {
			return invalid()
		}
	}
	for _, metric := range object(at(task, "evaluation_protocol", "metric_definitions")) {
		for _, ref := range array(at(metric, "evidence_requirements")) {
			if _, present := bindings[stringAt(ref, fieldRefID)]; !present {
				return invalid()
			}
		}
	}
	for _, result := range object(at(run, "result_summaries")) {
		metric := at(task, "evaluation_protocol", "metric_definitions", stringAt(result, "metric_id"))
		ids := rowSet(at(result, fieldEvidenceRefs), fieldRefID)
		for _, requirement := range array(at(metric, "evidence_requirements")) {
			if !evidenceBindingMatches(bindings[stringAt(requirement, fieldRefID)], requirement, ids) {
				return invalid()
			}
		}
	}
	return nil
}
func evidenceBindingMatches(binding evidenceBinding, ref any, artifacts map[string]bool) bool {
	if stringAt(ref, fieldRefKind) != termEvidence || stringAt(ref, fieldRefID) != binding.requirement || binding.requirement == "" || artifacts != nil && !artifacts[binding.artifactID] {
		return false
	}
	if at(ref, fieldRefVersion) != nil && stringAt(ref, fieldRefVersion) != binding.version {
		return false
	}
	if at(ref, "ref_digest") != nil && !strings.EqualFold(stringAt(ref, "ref_digest"), binding.digest) {
		return false
	}
	return at(ref, "ref_path") == nil || stringAt(ref, "ref_path") == binding.locator
}
