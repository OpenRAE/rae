package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

const termMaterializationArchiveRecordV1 = "materialization-archive-record-v1"

// MaterializationArchive admits the optional typed inventory under the
// execution context, inserts it into the record, applies the published
// defaults and admits the serialized record. The record must omit its
// inventory: this operation owns that member. The context supplies the
// protected SDL bytes for the record.
func MaterializationArchive(v *Validator, record binding.MaterializationArchiveRecordV1, inventory *binding.BackendRuntimeDescendantsV1, limits ingress.Limits, context MaterializationInventoryContext) (validation.Value, error) {
	if context == nil {
		return validation.Value{}, contextRequired()
	}
	if record.Inventory.Present() {
		return validation.Value{}, invalid()
	}
	data, err := json.Marshal(record)
	if err != nil {
		return validation.Value{}, invalid()
	}
	document, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return validation.Value{}, err
	}
	if inventory != nil {
		report, reportErr := v.admitInventory(*inventory, limits, context)
		if reportErr != nil {
			return validation.Value{}, reportErr
		}
		object(document)["inventory"] = report
	}
	if data, err = json.Marshal(document); err != nil {
		return validation.Value{}, invalid()
	}
	view, err := v.low.Defaulted(termMaterializationArchiveRecordV1, data, limits)
	if err != nil {
		return validation.Value{}, err
	}
	if data, err = json.Marshal(view); err != nil {
		return validation.Value{}, invalid()
	}
	return v.admitArchive(data, limits, context)
}

// RestoreMaterializationArchive admits serialized archive bytes against the
// protected SDL bytes that the context supplies. It returns the record, its
// schema-checked inventory or nil, and the admitted value. The archive binding
// joins the inventory to the attested SDL provenance.
func RestoreMaterializationArchive(v *Validator, data []byte, limits ingress.Limits, context MaterializationInventoryContext) (binding.MaterializationArchiveRecordV1, *binding.BackendRuntimeDescendantsV1, validation.Value, error) {
	admitted, err := v.admitArchive(data, limits, context)
	if err != nil {
		return binding.MaterializationArchiveRecordV1{}, nil, validation.Value{}, err
	}
	transport, err := admitted.Transport()
	record, ok := transport.(binding.MaterializationArchiveRecordV1)
	if err != nil || !ok {
		return binding.MaterializationArchiveRecordV1{}, nil, validation.Value{}, invalid()
	}
	raw, present := record.Inventory.Value()
	if !present {
		return record, nil, admitted, nil
	}
	decoded, err := v.low.DecodeSchema(termBackendRuntimeDescendantsV1, raw, limits)
	report, ok := decoded.(binding.BackendRuntimeDescendantsV1)
	if err != nil || !ok {
		return binding.MaterializationArchiveRecordV1{}, nil, validation.Value{}, invalid()
	}
	return record, &report, admitted, nil
}

// admitInventory admits a typed inventory under the execution context and
// returns its admitted JSON form.
func (e *Validator) admitInventory(inventory binding.BackendRuntimeDescendantsV1, limits ingress.Limits, context MaterializationInventoryContext) (any, error) {
	data, err := json.Marshal(inventory)
	if err != nil {
		return nil, invalid()
	}
	admitted, err := e.Validate(termBackendRuntimeDescendantsV1, data, limits, context)
	if err != nil {
		return nil, err
	}
	return ingress.Parse(admitted.JSON(), limits, ingress.Object)
}

// admitArchive admits record bytes with the protected SDL bytes for them. The
// owner reads only bounded, schema-valid record bytes.
func (e *Validator) admitArchive(data []byte, limits ingress.Limits, context MaterializationInventoryContext) (validation.Value, error) {
	if context == nil {
		return validation.Value{}, contextRequired()
	}
	// Bound and schema-check the record before the trusted owner reads it.
	if err := e.low.CheckSchema(termMaterializationArchiveRecordV1, data, limits); err != nil {
		return validation.Value{}, err
	}
	source, err := context.RetainedMaterializationSDL(data)
	if err != nil {
		return validation.Value{}, invalid()
	}
	return e.Validate(termMaterializationArchiveRecordV1, data, limits, materializationRetainedArchive{context, source})
}
