package authoring

import (
	"slices"
	"strings"
	"unicode"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func (w *normalizer) profileSchemaOutput(pointer string, fields ordered, order []string) (ordered, error) {
	if pointer != "#/$defs/DomainProfileSchemaModel" || object(fields)["schema_digest"] != nil {
		return fields, nil
	}
	document := object(fields)["schema_document"]
	if object(document) == nil {
		return nil, invalid()
	}
	raw, err := encode(document, w.workingLimit, false)
	if err != nil {
		return nil, err
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return nil, err
	}
	return setModelField(fields, order, "schema_digest", digest.SHA256(canonical)), nil
}

func modelOutput(pointer string, fields ordered, order []string) ordered {
	if pointer == "#/$defs/ParticipantActionArgumentDefinition" {
		return actionArgumentOutput(fields, order)
	}
	if pointer != "#/$defs/RuntimeIdentityAttribute" {
		return fields
	}
	value := object(fields)
	origin, present := value["origin"]
	if !present {
		origin = unknownTerm
	}
	provenance := text(value["provenance"])
	if origin != unknownTerm || provenance == "" || provenance == unknownTerm {
		return fields
	}
	return setModelField(fields, order, "origin", value["provenance"])
}

func setModelField(fields ordered, order []string, name string, value any) ordered {
	for i, field := range fields {
		if field.name == name {
			fields[i].value = value
			fields[i].omit = false
			return fields
		}
	}
	wanted, position := slices.Index(order, name), len(fields)
	for i, field := range fields {
		if rank := slices.Index(order, field.name); rank >= 0 && wanted >= 0 && rank > wanted {
			position = i
			break
		}
	}
	fields = append(fields, field{})
	copy(fields[position+1:], fields[position:])
	fields[position] = field{name: name, value: value}
	return fields
}

func actionArgumentOutput(fields ordered, order []string) ordered {
	if text(object(fields)["normalization"]) != "trim" {
		return fields
	}
	for i, field := range fields {
		if field.name == "allowed_values" || field.name == defaultField {
			fields[i].value = trimArgumentValue(field.value)
		}
	}
	values := object(fields)["allowed_values"]
	if values == nil {
		values = []any{}
	}
	return setModelField(fields, order, "allowed_values", values)
}

func trimArgumentValue(value any) any {
	switch v := value.(type) {
	case string:
		return strings.TrimFunc(v, func(r rune) bool { return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f })
	case []any:
		for i, child := range v {
			v[i] = trimArgumentValue(child)
		}
	}
	return value
}
