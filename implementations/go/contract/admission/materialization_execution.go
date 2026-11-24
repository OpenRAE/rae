package admission

import (
	"encoding/json"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type materializationExecution struct {
	owner                            *Validator
	context                          MaterializationExecutionContext
	snapshot                         MaterializationExecutionSnapshot
	plan, manifest, previous, actual any
	domain                           string
	original, current                *materializationCompiled
}

func (e *Validator) materializationExecutionRules() map[string]definition {
	return map[string]definition{
		"backend-materialization-submission-admission":  {check: e.materializationExecutionCheck, contextual: true, requiresContext: true},
		"materialized-sdl-source-and-inventory-binding": {check: e.materializationExecutionCheck, contextual: true, requiresContext: true},
	}
}

func (e *Validator) materializationExecutionCheck(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(MaterializationExecutionContext)
	if !ok {
		return contextRequired()
	}
	r := materializationExecution{owner: e, context: context, snapshot: context.MaterializationExecutionSnapshot()}
	if err = r.load(); err != nil {
		return err
	}
	source := r.snapshot.Submission
	if i.Key.ContractID == termBackendMaterializationAttestationV1 {
		source = []byte(stringAt(i.Instance, "sdl"))
		if string(source) != string(r.snapshot.Submission) {
			return invalid()
		}
	}
	if err = r.compile(source); err != nil {
		return err
	}
	if i.Key.ContractID == termMaterializedScenarioV1 && !equal(i.Instance, r.current.document) {
		return invalid()
	}
	return r.check()
}

func (r *materializationExecution) load() error {
	var err error
	switch r.snapshot.Plan.ContractID() {
	case termProvisioningPlanV1:
		r.domain = termProvisioning
	case termOrchestrationPlanV1:
		r.domain = termOrchestration
	case termEvaluationPlanV1:
		r.domain = termEvaluation
	default:
		return invalid()
	}
	r.plan, err = materializationAdmitted(r.snapshot.Plan, r.snapshot.Plan.ContractID())
	if err != nil {
		return err
	}
	r.manifest, err = materializationAdmitted(r.snapshot.Manifest, termBackendManifestV2)
	if err != nil {
		return err
	}
	r.actual, err = r.owner.flowAdmittedDocument(termRuntimeSnapshotV1, r.snapshot.Actual)
	if err != nil {
		return err
	}
	r.previous, err = r.owner.materializationPredecessor(r.snapshot.Predecessor)
	return err
}

func materializationAdmitted(admitted validation.Value, id string) (any, error) {
	if admitted.ContractID() != id {
		return nil, invalid()
	}
	return ingress.Parse(admitted.JSON(), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
}

func (e *Validator) materializationPredecessor(raw []byte) (any, error) {
	v, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, err
	}
	if _, present := object(v)[termSchemaVersion]; present {
		return nil, invalid()
	}
	if err = value.Validate(v, value.Runtime()); err != nil {
		return nil, invalid()
	}
	envelope := maps.Clone(object(v))
	envelope[termSchemaVersion] = "runtime-snapshot/v1"
	encoded, err := json.Marshal(envelope)
	if err != nil {
		return nil, invalid()
	}
	if _, err = e.contextDocument(termRuntimeSnapshotV1, encoded); err != nil {
		return nil, err
	}
	return v, nil
}

func (r *materializationExecution) compile(source []byte) error {
	originalSource, err := materializationSource(at(r.plan, "materialization_source"))
	if err != nil {
		return err
	}
	originalBytes, err := json.Marshal(at(originalSource, kindScenario))
	if err != nil {
		return invalid()
	}
	request := MaterializationCompileRequest{ContractID: termInstantiatedScenarioV1, Source: originalBytes, Plan: r.snapshot.Plan, Predecessor: r.snapshot.Predecessor}
	r.original, err = r.owner.materializationCompile(r.context, request)
	if err != nil {
		return err
	}
	request.ContractID = termMaterializedScenarioV1
	request.Source = source
	r.current, err = r.owner.materializationCompile(r.context, request)
	return err
}

func materializationSource(source any) (any, error) {
	raw := []byte(stringAt(source, "snapshot"))
	if len(raw) == 0 || len(raw) > value.MaterializationBytes {
		return nil, invalid()
	}
	v, err := ingress.Parse(raw, ingress.Limits{MaxBytes: value.MaterializationBytes, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, err
	}
	if err = value.Validate(v, value.Runtime()); err != nil {
		return nil, invalid()
	}
	if len(object(v)) != 2 || stringAt(v, "profile") != "raes-sdl-instantiated-snapshot/v2" || object(at(v, kindScenario)) == nil {
		return nil, invalid()
	}
	commitment, err := jsonDigest(v)
	if err != nil {
		return nil, err
	}
	if commitment != stringAt(source, "instantiated_digest") || !equal(at(v, kindScenario, "instantiation_provenance", "authored_digest", "value"), at(source, "authored_digest")) {
		return nil, invalid()
	}
	return v, nil
}

func (r *materializationExecution) check() error {
	if err := r.binding(); err != nil {
		return err
	}
	if err := materializationOrigins(r.original, r.current); err != nil {
		return err
	}
	if err := r.inventory(); err != nil {
		return err
	}
	return r.nodeBindings()
}

func (r *materializationExecution) binding() error {
	provenance := at(r.current.full, "materialization_provenance")
	source := at(r.plan, "materialization_source")
	if at(provenance, "inventory") != nil && (r.domain != termProvisioning || !set(at(r.manifest, "supported_contract_versions"))[termBackendRuntimeDescendantsV1]) {
		return invalid()
	}
	planDigest, err := jsonDigest(map[string]any{"domain": r.domain, "plan": materializationPlanProjection(r.plan)})
	if err != nil {
		return err
	}
	previousDigest, err := jsonDigest(r.previous)
	if err != nil {
		return err
	}
	manifestDigest, err := jsonDigest(r.manifest)
	if err != nil {
		return err
	}
	expected := []any{at(source, "authored_digest"), at(source, "instantiated_digest"), planDigest, previousDigest, at(r.plan, "operation_id"), at(source, "run_id"), at(r.manifest, termIdentity, termName), at(r.manifest, termIdentity, "version"), at(r.manifest, "realization_envelope", "configuration_digest"), manifestDigest}
	observed := []any{at(provenance, "authored_digest", "value"), at(provenance, "instantiated_digest", "value"), at(provenance, "plan_digest"), at(provenance, "predecessor_digest"), at(provenance, "operation_id"), at(provenance, "run_id"), at(provenance, "producer", termName), at(provenance, "producer", "version"), at(provenance, "producer", "configuration_digest"), at(provenance, "producer", "manifest_digest")}
	return require(at(r.manifest, "realization_envelope") != nil && equal(expected, observed))
}

// The plan owner supplies its completed published projection. These root fields
// have explicit serialization exclusions; arbitrary payload nulls stay intact.
func materializationPlanProjection(plan any) any {
	result := maps.Clone(object(plan))
	for key, v := range result {
		if v == nil {
			delete(result, key)
		}
	}
	if stringAt(result, "purpose") == termExecution {
		delete(result, "purpose")
	}
	for _, key := range []string{"augmentation_scope_required", "inventory_refresh"} {
		if result[key] == false {
			delete(result, key)
		}
	}
	return result
}
