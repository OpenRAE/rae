package realization

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strconv"
)

// Native model bytes preserve constructor field order. Keep the order at this
// input boundary: scope arrays and their integrity bindings are ordered data.
func realizationFieldOrder(raw []byte) (map[string][]string, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	reader := realizationOrderReader{decoder: decoder, order: map[string][]string{}}
	return reader.order, reader.value("")
}

type realizationOrderReader struct {
	decoder *json.Decoder
	order   map[string][]string
}

func (r *realizationOrderReader) value(pointer string) error {
	token, err := r.decoder.Token()
	if err != nil {
		return err
	}
	switch token {
	case json.Delim('{'):
		return r.object(pointer)
	case json.Delim('['):
		for index := 0; r.decoder.More(); index++ {
			if childErr := r.value(metadataPointer(pointer, strconv.Itoa(index))); childErr != nil {
				return childErr
			}
		}
		_, err = r.decoder.Token()
		return err
	default:
		return nil
	}
}
func (r *realizationOrderReader) object(pointer string) error {
	for r.decoder.More() {
		key, err := r.decoder.Token()
		if err != nil {
			return err
		}
		name := ownedProjection[string](key)
		r.order[pointer] = append(r.order[pointer], name)
		if err := r.value(metadataPointer(pointer, name)); err != nil {
			return err
		}
	}
	_, err := r.decoder.Token()
	return err
}

func (m *concernMetadata) fieldOrder(record map[string]any, sourcePointer string) []string {
	order := m.concern.input.fieldOrder[m.concern.pointer+sourcePointer]
	if m.concern.definition.kind == termLinuxCapabilities {
		if sourcePointer == "" {
			order = []string{termRequired, termEffective, termAdd, termDrop, "process_overrides"}
		}
		// Overrides preserve the specialized projector's subject and set order.
		if _, exists := record[termSubject]; exists {
			order = []string{termSubject, termScope, termEffective, termAdd, termDrop, termIdentityMarker}
		}
	}
	result := make([]string, 0, len(record))
	seen := map[string]bool{}
	for _, name := range order {
		if _, exists := record[name]; exists {
			result = append(result, name)
			seen[name] = true
		}
	}
	for _, name := range slices.Sorted(maps.Keys(record)) {
		if !seen[name] {
			result = append(result, name)
		}
	}
	return result
}
