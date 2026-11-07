package admission

func (e *Validator) referenceModels(v any) error {
	for _, model := range object(at(v, "models")) {
		if !e.knownFamily(stringAt(model, "concept_family")) {
			return invalid()
		}
		if err := e.referenceModelBindings(model); err != nil {
			return err
		}
	}
	return nil
}
func (e *Validator) referenceModelBindings(model any) error {
	fields := stringsOf(at(model, "key_fields"))
	if !unique(fields) {
		return invalid()
	}
	bindings := append([]any{at(model, "authoritative_schema")}, array(at(model, "reused_schemas"))...)
	seen := map[string]bool{}
	for _, binding := range bindings {
		id, pointer, path := stringAt(binding, "contract_id"), stringAt(binding, "schema_pointer"), stringAt(binding, "instance_path")
		key := join(id, pointer, path)
		if seen[key] {
			return invalid()
		}
		seen[key] = true
		if err := e.low.CheckReferenceBinding(id, pointer, path, fields); err != nil {
			return err
		}
	}
	return nil
}
