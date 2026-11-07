package governance

import (
	"encoding/json"
	"math"
	"math/big"
	"regexp"
	"slices"
	"strings"

	"golang.org/x/text/cases"
)

var atlasSlugSeparators = regexp.MustCompile(`[^a-z0-9]+`)

type atlasSequence struct {
	value   *mapping
	number  *big.Rat
	text    string
	numeric bool
}

func extractAtlasTactics(payload *mapping) ([]any, error) {
	if err := atlasSnapshotMetadata(payload); err != nil {
		return nil, err
	}
	raw := object(object(payload.get("relationships")).get(atlasMatrixID))
	value := raw.get("sequences")
	if !raw.has("sequences") {
		value = []any{}
	}
	sequences, err := atlasSequences(value)
	if err != nil {
		return nil, err
	}
	return atlasTacticRows(object(payload.get("tactics")), sequences)
}

func atlasSnapshotMetadata(payload *mapping) error {
	if payload.get("format-version") != "6.0.0" {
		return policyInputError("ATLAS payload format-version is " + pythonRepr(payload.get("format-version")) + "; expected '6.0.0'")
	}
	collection := object(payload.get("collection"))
	if collection.get("id") != "ATLAS-collection" || collection.get("version") != "2026.06" {
		return policyInputError("ATLAS payload collection id/version does not match the pinned source metadata")
	}
	if object(payload.get("matrix")).get("id") != atlasMatrixID {
		return policyInputError("ATLAS payload matrix id is " + pythonRepr(object(payload.get("matrix")).get("id")) + "; expected 'ATLAS-matrix'")
	}
	return nil
}

func atlasTacticRows(tactics *mapping, sequences []atlasSequence) ([]any, error) {
	rows := []any{}
	for _, sequence := range sequences {
		item := sequence.value
		if item.get("source") != atlasMatrixID || item.get("relationship-type") != "sequences" {
			return nil, policyInputError("ATLAS matrix sequence has unexpected shape: " + pythonRepr(item))
		}
		if !item.has("target") {
			return nil, policyInputError("ATLAS matrix sequence has no target")
		}
		id := pythonStr(item.get("target"))
		tactic := object(tactics.get(id))
		if tactic == nil {
			return nil, policyInputError("ATLAS matrix references missing tactic " + pythonRepr(id))
		}
		row, err := atlasTacticRow(id, tactic, item)
		if err != nil {
			return nil, err
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func atlasSequences(raw any) ([]atlasSequence, error) {
	values, ok := raw.([]any)
	if !ok {
		return nil, policyInputError("ATLAS sequences must be an array")
	}
	sequences := make([]atlasSequence, 0, len(values))
	for _, value := range values {
		item := object(value)
		if item == nil || !item.has("position") {
			return nil, policyInputError("ATLAS sequence has no position")
		}
		position := item.get("position")
		number, numeric := extractionNumber(position)
		text, textual := position.(string)
		if !numeric && !textual {
			return nil, policyInputError("ATLAS sequence position is not comparable")
		}
		if len(sequences) > 0 && sequences[0].numeric != numeric {
			return nil, policyInputError("ATLAS sequence positions have incompatible types")
		}
		sequences = append(sequences, atlasSequence{item, number, text, numeric})
	}
	slices.SortStableFunc(sequences, func(a, b atlasSequence) int {
		if a.numeric {
			return a.number.Cmp(b.number)
		}
		return strings.Compare(a.text, b.text)
	})
	return sequences, nil
}

func atlasTacticRow(id string, tactic, sequence *mapping) (*mapping, error) {
	if tactic.get("object-type") != "tactic" || tactic.get("id") != id {
		return nil, policyInputError("ATLAS tactic " + pythonRepr(id) + " has unexpected object-type/id")
	}
	for _, field := range []string{nameField, descriptionField, uuidField, "created-date", "modified-date"} {
		if !tactic.has(field) {
			return nil, policyInputError("ATLAS tactic is missing a required field")
		}
	}
	position, valid := extractionInteger(sequence.get("position"))
	if !valid {
		return nil, policyInputError("ATLAS sequence position is not an integer")
	}
	reference := object(tactic.get("attack-reference"))
	if truth(tactic.get("attack-reference")) && reference == nil {
		return nil, policyInputError("ATLAS attack-reference must be a mapping")
	}
	row := newMapping()
	row.set(tacticIDField, id)
	row.set(shortnameField, strings.Trim(atlasSlugSeparators.ReplaceAllString(cases.Fold().String(pythonStr(tactic.get(nameField))), "-"), "-"))
	row.set(nameField, pythonStr(tactic.get(nameField)))
	row.set(descriptionField, pythonStr(tactic.get(descriptionField)))
	row.set(urlField, "https://atlas.mitre.org/tactics/"+id+"/")
	row.set("position", position)
	for _, field := range []struct{ out, in string }{{uuidField, uuidField}, {"created_date", "created-date"}, {"modified_date", "modified-date"}} {
		row.set(field.out, pythonStr(tactic.get(field.in)))
	}
	row.set("attack_reference_id", reference.get("id"))
	row.set("attack_reference_url", reference.get(urlField))
	return row, nil
}

func extractionNumber(value any) (*big.Rat, bool) {
	switch value := value.(type) {
	case json.Number:
		r, ok := new(big.Rat).SetString(string(value))
		return r, ok
	case bool:
		if value {
			return new(big.Rat).SetInt64(1), true
		}
		return new(big.Rat), true
	case float64:
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return nil, false
		}
		return new(big.Rat).SetFloat64(value), true
	default:
		return nil, false
	}
}
func extractionInteger(value any) (json.Number, bool) {
	if text, ok := value.(string); ok {
		integer, valid := pythonIntegerText(text)
		return json.Number(integer), valid
	}
	number, valid := extractionNumber(value)
	if !valid {
		return "", false
	}
	return json.Number(new(big.Int).Quo(number.Num(), number.Denom()).String()), true
}
