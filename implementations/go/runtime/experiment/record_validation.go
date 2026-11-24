package experiment

import (
	"context"
	"encoding/json"
	"io"
	"reflect"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
)

func planAdmission(plan binding.AdmittedTrialPlanV1) (validation.Value, error) {
	owner, err := experimentOwner()
	if err != nil {
		return validation.Value{}, err
	}
	raw, err := json.Marshal(plan)
	if err != nil {
		return validation.Value{}, err
	}
	return owner.Validate("admitted-trial-plan-v1", raw, runtimeIngress(), nil)
}

type recordContext struct {
	task, processor, backend, cleanup []byte
	tasks, runs                       [][]byte
}

func (c recordContext) CleanupPlan() []byte       { return slices.Clone(c.cleanup) }
func (c recordContext) ExperimentTask() []byte    { return slices.Clone(c.task) }
func (c recordContext) ProcessorManifest() []byte { return slices.Clone(c.processor) }
func (c recordContext) BackendManifest() []byte   { return slices.Clone(c.backend) }
func (c recordContext) ProcessorManifestDigest() string {
	raw, err := canonical(json.RawMessage(c.processor))
	if err != nil {
		return ""
	}
	return digest.SHA256(raw)
}
func (c recordContext) BackendManifestDigest() string {
	raw, err := canonical(json.RawMessage(c.backend))
	if err != nil {
		return ""
	}
	return digest.SHA256(raw)
}
func (c recordContext) ExperimentTasks() [][]byte { return c.tasks }
func (c recordContext) ExperimentRuns() [][]byte  { return c.runs }
func (c *coordinator) recordContext(source RecordSource) (recordContext, error) {
	result := recordContext{}
	var err error
	result.task, err = json.Marshal(c.options.Inputs.Task)
	if err != nil {
		return result, err
	}
	plan, err := transportView(source.Plan)
	if err != nil {
		return result, err
	}
	attempt := decisionMap(source.Attempts[0])
	entryID := text(attempt, termPlanEntryID)
	result.cleanup, err = json.Marshal(at(plan, "cleanup_plans", text(plan, "entries", entryID, "execution_controls", "cleanup_plan_ref")))
	if err != nil {
		return result, err
	}
	if err = c.recordManifests(&result, at(plan, "entries", entryID, "apparatus", "manifest_refs")); err != nil {
		return result, err
	}
	result.tasks = [][]byte{result.task}
	return result, nil
}
func (c *coordinator) recordManifests(result *recordContext, refs any) error {
	owner, err := experimentOwner()
	if err != nil {
		return err
	}
	for _, ref := range array(refs) {
		kind := text(ref, "subject_ref", termRefKind)
		if kind != "processor" && kind != termBackend {
			continue
		}
		target := &result.processor
		if kind == termBackend {
			target = &result.backend
		}
		if *target != nil {
			return integrity()
		}
		*target, err = c.selectedRecordManifest(owner, ref, kind)
		if err != nil {
			return err
		}
	}
	return nil
}
func (c *coordinator) validateRun(ctx context.Context, source RecordSource, run binding.ExperimentRunV1, reader EvidenceReader) error {
	_, err := ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (result struct{}, checkErr error) {
		evidence, closers, openErr := c.openEvidence(work, source, run, reader)
		defer func() {
			if closeErr := closeReaders(work, closers); checkErr == nil {
				checkErr = closeErr
			}
		}()
		if openErr != nil {
			return struct{}{}, openErr
		}
		owner, ownerErr := experimentOwner()
		if ownerErr != nil {
			return struct{}{}, ownerErr
		}
		authority, authorityErr := c.recordContext(source)
		if authorityErr != nil {
			return struct{}{}, authorityErr
		}
		taskValue, taskErr := owner.Validate("experiment-task-v1", authority.task, runtimeIngress(), authority)
		if taskErr != nil {
			return struct{}{}, taskErr
		}
		raw, encodeErr := json.Marshal(run)
		if encodeErr != nil {
			return struct{}{}, encodeErr
		}
		runValue, runErr := owner.Validate("experiment-run-v1", raw, runtimeIngress(), authority)
		if runErr != nil {
			return struct{}{}, runErr
		}
		return struct{}{}, admission.ValidateExperimentRun(owner, taskValue, runValue, evidence)
	})
	return err
}
func (c *coordinator) openEvidence(ctx context.Context, source RecordSource, run binding.ExperimentRunV1, reader EvidenceReader) (*admission.ExperimentEvidenceInputs, []io.Closer, error) {
	last := decisionMap(source.Attempts[len(source.Attempts)-1])
	capture := attemptObservations(source.Observations, text(last, termExecutionAttemptID))[termCapture]
	if !truth(at(capture, "observation", "complete")) {
		return nil, nil, integrity()
	}
	if reader == nil {
		return nil, nil, nil
	}
	detached, err := copyDTO(run)
	if err != nil {
		return nil, nil, err
	}
	opened, err := foreignCall(ctx, func(work context.Context) (EvidenceInputs, error) { return reader.Open(work, detached) })
	closers := slices.Clone(opened.Readers)
	for _, stream := range opened.Inputs.ArtifactReaders {
		if closer, ok := stream.(io.Closer); ok {
			closers = append(closers, closer)
		}
	}
	if err != nil {
		return nil, closers, err
	}
	if err = c.validateEvidenceInputs(source, opened.Inputs); err != nil {
		return nil, closers, err
	}
	return &opened.Inputs, closers, nil
}
func closeReaders(ctx context.Context, closers []io.Closer) error {
	var closeFailure error
	seen := map[io.Closer]bool{}
	for _, closer := range closers {
		if missing(closer) {
			continue
		}
		if reflect.TypeOf(closer).Comparable() {
			if seen[closer] {
				continue
			}
			seen[closer] = true
		}
		if _, err := foreignCall(ctx, func(context.Context) (struct{}, error) { return struct{}{}, closer.Close() }); err != nil {
			closeFailure = integrity()
		}
	}
	return closeFailure
}
func (c *coordinator) validateEvidenceInputs(source RecordSource, inputs admission.ExperimentEvidenceInputs) error {
	if len(inputs.CaptureSpecs) != len(c.options.Inputs.CaptureSpecs) {
		return integrity()
	}
	for key, spec := range c.options.Inputs.CaptureSpecs {
		v, ok := inputs.CaptureSpecs[key]
		if !ok || v.ContractID() != "experiment-capture-spec-v1" || !same(json.RawMessage(v.JSON()), spec) {
			return integrity()
		}
	}
	evidence, err := observedEvidence(source.Observations, "")
	if err != nil {
		return err
	}
	for key, record := range inputs.EvidenceRecords {
		if record.ContractID() != "experiment-evidence-record-v1" {
			return integrity()
		}
		var view any
		if json.Unmarshal(record.JSON(), &view) != nil || text(view, "evidence_record_id") != key {
			return integrity()
		}
		found := slices.ContainsFunc(evidence, func(retained any) bool { return same(retained, view) })
		if !found {
			return integrity()
		}
	}
	return nil
}

func (c *coordinator) selectedRecordManifest(owner *admission.Validator, ref any, kind string) ([]byte, error) {
	key := trial.ApparatusManifestKey{ComponentKind: kind, ComponentName: text(ref, "subject_ref", "ref_id"), ComponentVersion: text(ref, "subject_ref", termRefVersion), ManifestVersion: text(ref, termRefVersion)}
	manifest, present := c.options.Inputs.ApparatusManifests[key]
	if !present {
		return nil, integrity()
	}
	raw, encodeErr := json.Marshal(manifest.Processor)
	if kind == termBackend {
		raw, encodeErr = json.Marshal(manifest.Backend)
	}
	if encodeErr != nil {
		return nil, encodeErr
	}
	projected, err := admission.ManifestModelProjection(owner, kind+"-manifest-v2", raw)
	if err != nil {
		return nil, err
	}
	canonicalRaw, canonicalErr := canonical(json.RawMessage(projected))
	if canonicalErr != nil || digest.SHA256(canonicalRaw) != text(ref, "ref_digest") {
		return nil, integrity()
	}
	return projected, nil
}
