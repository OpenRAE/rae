package admission

import (
	"encoding/json"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type materializationInventory struct {
	execution                   materializationExecution
	context                     MaterializationInventoryContext
	report, preceding, envelope any
	originals                   map[string]any
	entries                     map[string]any
}

func (e *Validator) materializationInventoryRules() map[string]definition {
	return map[string]definition{"runtime-descendant-inventory-admission": {check: e.materializationDescendants, contextual: true, requiresContext: true}}
}
func (e *Validator) materializationDescendants(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(MaterializationInventoryContext)
	if !ok {
		return contextRequired()
	}
	r := materializationInventory{context: context, execution: materializationExecution{owner: e, context: context, snapshot: context.MaterializationExecutionSnapshot()}}
	if err = r.execution.load(); err != nil {
		return err
	}
	if r.execution.domain != termProvisioning || !set(at(r.execution.manifest, "supported_contract_versions"))[termBackendRuntimeDescendantsV1] {
		return invalid()
	}
	if err = r.execution.compile(r.execution.snapshot.Submission); err != nil {
		return err
	}
	r.report = at(r.execution.current.full, "materialization_provenance", "inventory")
	candidate, err := e.defaulted(termBackendRuntimeDescendantsV1, i.Instance)
	if err != nil {
		return err
	}
	if r.report == nil || !equal(candidate, r.report) {
		return invalid()
	}
	return r.admit()
}
func (r *materializationInventory) admit() error {
	if err := r.boundReport(); err != nil {
		return err
	}
	if err := r.execution.binding(); err != nil {
		return err
	}
	if err := materializationOrigins(r.execution.original, r.execution.current); err != nil {
		return err
	}
	r.originals = materializationScope(r.execution.original.resources, termProvisioning)
	if err := r.predecessor(); err != nil {
		return err
	}
	if err := r.lineage(); err != nil {
		return err
	}
	if err := r.project(); err != nil {
		return err
	}
	if err := r.membership(); err != nil {
		return err
	}
	if err := r.capabilities(); err != nil {
		return err
	}
	if err := r.augmentation(); err != nil {
		return err
	}
	projected := maps.Clone(object(r.execution.actual))
	projected["entries"] = r.entries
	r.execution.actual = projected
	if err := r.execution.check(); err != nil {
		return err
	}
	return r.selections()
}

func (r *materializationInventory) boundReport() error {
	plan := r.execution.plan
	source := at(plan, "materialization_source")
	return require(at(plan, "inventory_attempt_id") != nil && at(source, "target_scope") != nil && equal(at(r.report, "attempt_id"), at(plan, "inventory_attempt_id")) && equal(at(r.report, "run_id"), at(source, "run_id")) && equal(at(r.report, "source_digest"), at(source, "instantiated_digest")) && equal(at(r.report, "target_scope"), at(source, "target_scope")))
}

type materializationRetainedArchive struct {
	MaterializationCompiler

	source []byte
}

func (c materializationRetainedArchive) ArchivedMaterializationSDL() []byte { return c.source }
func (r *materializationInventory) predecessor() error {
	source, manifest := at(r.execution.plan, "materialization_source"), r.execution.manifest
	var selected any
	for _, record := range array(at(r.execution.previous, "materialization_attestations")) {
		if equal(at(record, "run_id"), at(source, "run_id")) && equal(at(record, "artifact", "source"), at(manifest, termIdentity, "name")) && at(record, "inventory") != nil {
			selected = record
		}
	}
	if selected == nil {
		return require(!boolean(at(r.execution.plan, "inventory_refresh")))
	}
	raw, err := json.Marshal(selected)
	if err != nil {
		return invalid()
	}
	data, err := r.context.RetainedMaterializationSDL(raw)
	if err != nil {
		return invalid()
	}
	archive := materializationRetainedArchive{r.context, data}
	if err = r.execution.owner.materializationArchive(validation.Invocation{Instance: selected, Context: archive}); err != nil {
		return err
	}
	compiled, err := r.execution.owner.materializationCompile(r.context, MaterializationCompileRequest{ContractID: termMaterializedScenarioV1, Source: data})
	if err != nil {
		return err
	}
	p := at(compiled.full, "materialization_provenance")
	r.preceding = at(selected, "inventory")
	manifestDigest, err := jsonDigest(manifest)
	if err != nil {
		return err
	}
	return require(equal(at(p, "instantiated_digest", "value"), at(source, "instantiated_digest")) && equal(at(p, "producer", "configuration_digest"), at(manifest, "realization_envelope", "configuration_digest")) && equal(at(r.preceding, "target_scope"), at(source, "target_scope")) && stringAt(p, "producer", "manifest_digest") == manifestDigest)
}
