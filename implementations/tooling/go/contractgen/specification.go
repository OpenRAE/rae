package contractgen

import (
	"bytes"
	"encoding/json"
	"errors"
	"io/fs"
	"maps"
	"slices"
	"strconv"
	"strings"
)

func checkSpecification(source fs.FS, entries []publication) error {
	data, err := fs.ReadFile(source, "specs/conformance/contract-invariant-rules.json")
	if err != nil {
		return err
	}
	var specification struct {
		Schema string           `json:"specification"`
		Rules  []map[string]any `json:"rules"`
	}
	if err = json.Unmarshal(data, &specification); err != nil {
		return err
	}
	if specification.Schema != "raes-contract-invariant-rules/v1" {
		return errors.New("unknown invariant specification")
	}
	var actual []map[string]any
	for _, entry := range entries {
		data, readErr := fs.ReadFile(source, entry.SchemaPath)
		if readErr != nil {
			return readErr
		}
		var root any
		if err = json.Unmarshal(data, &root); err != nil {
			return err
		}
		actual = append(actual, ruleSpecifications(root, entry.ID, "#")...)
	}
	actualBytes, err := specificationBytes(actual)
	if err != nil {
		return err
	}
	expectedBytes, err := specificationBytes(specification.Rules)
	if err != nil {
		return err
	}
	if !bytes.Equal(actualBytes, expectedBytes) {
		return errors.New("invariant specifications do not match the published rules")
	}
	return nil
}

func specificationBytes(rows []map[string]any) ([]byte, error) {
	encoded := make([]string, 0, len(rows))
	for _, row := range rows {
		data, err := json.Marshal(row)
		if err != nil {
			return nil, err
		}
		encoded = append(encoded, string(data))
	}
	slices.Sort(encoded)
	return []byte(strings.Join(encoded, "\n")), nil
}

func ruleSpecifications(node any, id, pointer string) []map[string]any {
	var result []map[string]any
	switch n := node.(type) {
	case map[string]any:
		result = append(result, specificationRows(n["x-raes-invariants"], id, pointer)...)
		for key, value := range n {
			token := strings.ReplaceAll(strings.ReplaceAll(key, "~", "~0"), "/", "~1")
			result = append(result, ruleSpecifications(value, id, pointer+"/"+token)...)
		}
	case []any:
		for index, value := range n {
			result = append(result, ruleSpecifications(value, id, pointer+"/"+strconv.Itoa(index))...)
		}
	}
	return result
}

func specificationRows(raw any, id, pointer string) []map[string]any {
	rows, _ := raw.([]any)
	var result []map[string]any
	for _, item := range rows {
		if row, ok := item.(map[string]any); ok {
			record := map[string]any{"contract_id": id, "schema_pointer": pointer}
			maps.Copy(record, row)
			result = append(result, record)
		}
	}
	return result
}
