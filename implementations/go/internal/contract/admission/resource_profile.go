package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// Profile schemas retain their original member order for the reference's
// bounded evaluator. Raw bytes are used only within this admission call.
func resourceProfileSchemas(data []byte) ([]json.RawMessage, error) {
	var wire struct {
		Capabilities struct {
			Runtime struct {
				Budgets struct {
					Context struct {
						Definitions []struct {
							Definition struct {
								ProfileSchema struct {
									Schema json.RawMessage `json:"schema_document"`
								} `json:"profile_schema"`
							} `json:"definition"`
						} `json:"definitions"`
					} `json:"domain_profile_context"`
				} `json:"resource_budgets"`
			} `json:"participant_runtime"`
		} `json:"capabilities"`
	}
	if err := json.Unmarshal(data, &wire); err != nil {
		return nil, invalid()
	}
	var schemas []json.RawMessage
	for _, row := range wire.Capabilities.Runtime.Budgets.Context.Definitions {
		schemas = append(schemas, row.Definition.ProfileSchema.Schema)
	}
	return schemas, nil
}
func checkResourceProfiles(root any, data []byte) error {
	caps := at(root, "capabilities", "participant_runtime", "resource_budgets")
	if caps == nil {
		return nil
	}
	schemas, err := resourceProfileSchemas(data)
	if err != nil {
		return err
	}
	for _, pool := range array(at(caps, "configured_pools")) {
		if object(at(pool, "resource_kind")) == nil {
			continue
		}
		admitted := false
		for _, reset := range stringsOf(at(caps, "supported_reset_modes")) {
			if resourceMeasureSupported(pool, reset, at(caps, "domain_profile_context"), schemas) {
				admitted = true
				break
			}
		}
		if !admitted {
			return invalid()
		}
	}
	return nil
}
func resourceMeasureSemantics() any {
	digest, err := jsonDigest(map[string]any{"contract": "participant-resource-measure/v1", "value": "unit, existing accounting mode, exact meter and existing reset mode", "effect": "existing integer budget/pool reservation, measured settlement, generation and evidence enforcement"})
	if err != nil {
		return nil
	}
	return map[string]any{termAuthority: "https://openrae.org/profiles", "contract_id": "participant-resource-measure", termRevision: "1", "digest": digest}
}
func resolveResourceDefinition(coordinate, context any) (any, int) {
	authorities := map[string]bool{}
	for _, row := range array(at(context, "namespace_admissions")) {
		if equal(at(row, "namespace"), at(coordinate, "namespace")) {
			authorities[stringAt(row, termAuthority)] = true
		}
	}
	if len(authorities) != 1 || !authorities[stringAt(coordinate, termAuthority)] {
		return nil, -1
	}
	found := -1
	var selected any
	digests := map[string]bool{}
	for index, row := range array(at(context, "definitions")) {
		definition := at(row, "definition")
		candidate := at(definition, "coordinate")
		if !matchingFields(candidate, coordinate, "namespace", termAuthority, termProfileID, termRevision) {
			continue
		}
		digests[stringAt(candidate, "definition_digest")] = true
		if equal(candidate, coordinate) {
			if found >= 0 {
				return nil, -1
			}
			found = index
			selected = definition
		}
	}
	if len(digests) != 1 {
		return nil, -1
	}
	return selected, found
}
func resourceMeasureSupported(pool any, reset string, context any, schemas []json.RawMessage) bool {
	definition, index := resolveResourceDefinition(at(pool, "resource_kind"), context)
	if definition == nil || index < 0 || index >= len(schemas) || !equal(at(definition, "semantic_contract"), resourceMeasureSemantics()) || !set(at(definition, "allowed_contexts"))["participant-resource-measure"] {
		return false
	}
	support := resourceProfileSupport(definition, context)
	if support == nil {
		return false
	}
	profile := at(definition, "profile_schema")
	if !set(at(support, "supported_schema_dialects"))[text(defaultMember(profile, "dialect", domainProfileDialect))] || !subset(stringsOf(at(profile, "required_vocabularies")), set(at(support, "supported_vocabularies"))) {
		return false
	}
	limits := at(context, "limits")
	bounded := validation.InertLimits{MaxBytes: 16777216, MaxDepth: profileLimit(limits, "max_depth", 16), MaxNodes: profileLimit(limits, "max_nodes", 4096), MaxScalarBytes: profileLimit(limits, "max_scalar_bytes", 1048576), MaxReferences: profileLimit(limits, "max_references", 128), MaxEvaluations: profileLimit(limits, "max_evaluations", 65536)}
	value := struct {
		Unit       string `json:"unit"`
		Accounting string `json:"accounting_mode"`
		Meter      string `json:"meter_profile_ref"`
		Reset      string `json:"reset"`
	}{stringAt(pool, "unit"), stringAt(pool, "accounting_mode"), stringAt(pool, "meter_profile_ref"), reset}
	raw, err := json.Marshal(value)
	return err == nil && validation.CheckInertSchema(schemas[index], raw, stringsOf(at(support, "supported_schema_keywords")), bounded) == nil
}
func resourceProfileSupport(definition, context any) any {
	var selected any
	for _, support := range array(at(context, "support_declarations")) {
		if equal(at(support, "coordinate"), at(definition, "coordinate")) && equal(at(support, "semantic_contract"), at(definition, "semantic_contract")) {
			if selected != nil {
				return nil
			}
			selected = support
		}
	}
	if selected == nil {
		return nil
	}
	operations := set(at(selected, "operations"))
	for _, operation := range []string{termExecution, "typed-report", "structural-validation", "semantic-validation"} {
		if !operations[operation] {
			return nil
		}
	}
	return selected
}
