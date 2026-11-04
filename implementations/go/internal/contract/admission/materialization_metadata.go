package admission

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func (e *Validator) materializationPhaseMetadata(result *materializationCompiled, c MaterializationCompilation) error {
	var err error
	if len(c.NodeCollection) > 0 {
		result.collection, err = e.low.DefaultedObjectFragment(termProvisioningPlanV1, "#/$defs/PreparedNodeCollectionAuthority", c.NodeCollection, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
		if err != nil {
			return err
		}
	}
	result.concerns, err = materializationRequirementMap(c.NodeConcerns)
	if err != nil {
		return err
	}
	result.prepared, err = materializationRequirementMap(c.PreparedNodeRequirements)
	if err != nil {
		return err
	}
	if len(c.OrdinarySelections) > 16384 || len(c.NodePresence) > 16384 || !materializationOrdinaryBound(c.OrdinarySelections) {
		return invalid()
	}
	result.ordinary = maps.Clone(c.OrdinarySelections)
	result.presence = map[string]map[string][]string{}
	remaining, work := 8*1048576, 100000
	for name, paths := range c.NodePresence {
		if err := materializationPresence(result, name, paths, &remaining, &work); err != nil {
			return err
		}
	}
	return nil
}
func materializationRequirementMap(rows map[string][][]byte) (map[string][]json.RawMessage, error) {
	if len(rows) > 16384 {
		return nil, invalid()
	}
	result := map[string][]json.RawMessage{}
	remaining := 64 * 1048576
	for key, items := range rows {
		if len(key) > 4096 || len(items) > 16384 {
			return nil, invalid()
		}
		for _, item := range items {
			if len(item) > remaining {
				return nil, invalid()
			}
			remaining -= len(item)
		}
		parsed, err := materializationRequirements(items)
		if err != nil {
			return nil, err
		}
		result[key] = parsed
	}
	return result, nil
}

func materializationPresence(result *materializationCompiled, name string, paths map[string][]string, remaining, work *int) error {
	*remaining -= len(name)
	if len(paths) > 16384 || *remaining < 0 {
		return invalid()
	}
	result.presence[name] = map[string][]string{}
	for path, children := range paths {
		*remaining -= len(path)
		*work -= len(children) + 1
		if *work < 0 {
			return invalid()
		}
		for _, child := range children {
			*remaining -= len(child)
		}
		if len(path) > 4096 || *remaining < 0 || *work < 0 || !flowUniqueReferences(children) {
			return invalid()
		}
		result.presence[name][path] = slices.Clone(children)
	}
	return nil
}

func materializationOrdinaryBound(fields map[string]string) bool {
	remaining := 8 * 1048576
	for path, field := range fields {
		remaining -= len(path) + len(field)
		if remaining < 0 || len(path) > 4096 || len(field) > 4096 {
			return false
		}
	}
	return true
}
