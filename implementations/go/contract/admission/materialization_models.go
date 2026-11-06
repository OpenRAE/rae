package admission

import (
	"regexp"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
)

var materializedToken = regexp.MustCompile(`\$\{(?:(?:[a-z0-9][a-z0-9_-]{0,63}|__private)\.)*[a-z0-9][a-z0-9_-]{0,63}\}`)

func materializationModel(name string, v any) (bool, error) {
	switch name {
	case "MaterializationSource":
		_, err := materializationSource(v)
		return true, err
	case "MaterializationOrigin":
		return true, materializationOrigin(v)
	case "MaterializedResourceBinding":
		return true, require(materializationQualified(stringAt(v, "node_name")) && (at(v, "source_node") == nil || materializationQualified(stringAt(v, "source_node"))))
	case "MaterializationProvenance":
		return true, materializationProvenance(v)
	case "RuntimeDescendantBinding":
		return true, descendantLocal(v)
	case "RuntimeInventoryReport":
		return true, inventoryLocal(v)
	default:
		return false, nil
	}
}

func materializationQualified(value string) bool {
	if value == "" || len(value) > 2048 {
		return false
	}
	parts := strings.Split(value, ".")
	for index, part := range parts {
		if !address.Valid("x."+part) || index == len(parts)-1 && part == "__private" {
			return false
		}
	}
	return true
}

func materializedLocal(v any) error {
	work := 0
	if !materializationConcrete(v, &work) {
		return invalid()
	}
	for _, origin := range array(at(v, "materialization_provenance", "origins")) {
		if stringAt(origin, "change") == termRemoved {
			continue
		}
		if _, present := pointerAt(v, stringAt(origin, "field_pointer")); !present {
			return invalid()
		}
	}
	for _, binding := range array(at(v, "materialization_provenance", "resource_bindings")) {
		if _, present := object(at(v, "nodes"))[stringAt(binding, "node_name")]; !present {
			return invalid()
		}
	}
	return nil
}

func materializationConcrete(v any, work *int) bool {
	*work++
	if *work > 100000 {
		return false
	}
	switch value := v.(type) {
	case string:
		return !materializedToken.MatchString(value)
	case map[string]any:
		for _, child := range value {
			if !materializationConcrete(child, work) {
				return false
			}
		}
	case []any:
		for _, child := range value {
			if !materializationConcrete(child, work) {
				return false
			}
		}
	}
	return true
}

func materializationOrigin(v any) error {
	pointer := stringAt(v, "field_pointer")
	return require(pointer != "" && !strings.HasPrefix(pointer, "/materialization_provenance") && (stringAt(v, "change") == termAdded) == (at(v, "source_pointer") == nil) && stringAt(v, "origin") == termBackendRealized)
}

func materializationProvenance(v any) error {
	if err := timestamps(v, "recorded_at"); err != nil {
		return err
	}
	origins := map[string]bool{}
	for _, origin := range array(at(v, "origins")) {
		kind := "present"
		if stringAt(origin, "change") == termRemoved {
			kind = termRemoved
		}
		key := join(kind, stringAt(origin, "field_pointer"))
		if origins[key] {
			return invalid()
		}
		origins[key] = true
	}
	rows := array(at(v, "resource_bindings"))
	addresses, nodes := map[string]bool{}, map[string]bool{}
	for _, row := range rows {
		index, err := materializationInstanceIndex(at(row, "instance_index"))
		if err != nil {
			return err
		}
		a, n := join(stringAt(row, "address"), index), join(stringAt(row, "node_name"), index)
		if addresses[a] || nodes[n] {
			return invalid()
		}
		addresses[a], nodes[n] = true, true
	}
	return nil
}

func materializationRecordsUnique(records any) bool {
	seen := map[string]bool{}
	for _, record := range array(records) {
		identity := join(stringAt(record, "run_id"), stringAt(record, "reference", "ref_id"))
		if seen[identity] {
			return false
		}
		seen[identity] = true
	}
	return true
}

func materializationInstanceIndex(v any) (string, error) {
	if v == nil {
		return termNull, nil
	}
	n, ok := number(v)
	if !ok || !n.IsInt() || n.Sign() < 0 {
		return "", invalid()
	}
	return n.Num().String(), nil
}

func descendantLocal(v any) error {
	return require(!equal(at(v, "address"), at(v, "parent_address")) && !equal(at(v, "address"), at(v, "source_address")) && (text(defaultMember(v, "state", termActive)) == termActive) == (at(v, "lifecycle") == nil))
}

func inventoryLocal(v any) error {
	rows := array(at(v, "descendants"))
	if len(rowSet(rows, "address")) != len(rows) || len(rowSet(rows, "native_identity_digest")) != len(rows) || len(rowTupleSet(at(v, "backend_selections"), "address", "field_path", "requirement_kind")) != len(array(at(v, "backend_selections"))) {
		return invalid()
	}
	for _, row := range rows {
		if err := descendantLocal(row); err != nil {
			return err
		}
		for _, receipt := range []any{at(row, "creation"), at(row, "lifecycle")} {
			if receipt != nil && !equal(at(receipt, "run_id"), at(v, "run_id")) {
				return invalid()
			}
		}
	}
	return nil
}
