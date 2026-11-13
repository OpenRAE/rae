package admission

import (
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// The fragment owner already admitted the exact JSON carriers. This walk
// accounts for the caller's narrower relation limits and their diagnostic
// paths; it does not accept additional values or invoke supplied methods.
type constraintValueAdmission struct {
	engine      *constraintEvaluation
	scalarBytes int
	failure     *constraintResult
}

func (b *constraintValueAdmission) fail(status, path, message string) bool {
	result := constraintFailure(status, path, message)
	b.failure = &result
	return false
}
func (b *constraintValueAdmission) walk(input any, path string, depth int) bool {
	if !b.engine.spend(depth) {
		return b.nodeFailure(path, depth)
	}
	switch current := input.(type) {
	case map[string]any:
		return b.record(current, path, depth)
	case []any:
		return b.sequence(current, path, depth)
	default:
		return b.scalar(current, path)
	}
}
func (b *constraintValueAdmission) nodeFailure(path string, depth int) bool {
	limit := "max_operations"
	if depth > b.engine.limits.MaxDepth {
		limit = "max_depth"
	} else if b.engine.nodes > b.engine.limits.MaxNodes {
		limit = "max_nodes"
	}
	return b.fail("limit-exceeded", path, "Realization value validation exceeded "+limit+".")
}
func (b *constraintValueAdmission) record(input map[string]any, path string, depth int) bool {
	if len(input) > b.engine.limits.MaxMembers {
		return b.fail("limit-exceeded", path, "Realization value validation exceeded max_members.")
	}
	for _, field := range constraintMetadataObject(input) {
		if !b.scalar(field.name, path) || !b.walk(field.value, constraintAdmissionPath(path, field.name), depth+1) {
			return false
		}
	}
	return true
}
func (b *constraintValueAdmission) sequence(input []any, path string, depth int) bool {
	if len(input) > b.engine.limits.MaxMembers {
		return b.fail("limit-exceeded", path, "Realization value validation exceeded max_members.")
	}
	for index, child := range input {
		if !b.walk(child, path+"/"+strconv.Itoa(index), depth+1) {
			return false
		}
	}
	return true
}
func (b *constraintValueAdmission) scalar(input any, path string) bool {
	size := constraintScalarBytes(input)
	if size > b.engine.limits.MaxScalarBytes {
		return b.fail("limit-exceeded", path, "Realization value validation exceeded max_scalar_bytes.")
	}
	b.scalarBytes += size
	if b.scalarBytes > b.engine.limits.MaxTotalScalarBytes {
		return b.fail("limit-exceeded", path, "Realization value validation exceeded max_total_scalar_bytes.")
	}
	if value.Validate(input, constraintScalarLimits(b.engine.limits)) != nil {
		return b.fail("invalid", path, "Realization value is not JSON-compatible.")
	}
	return true
}
