package admission

import (
	"reflect"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// CheckPreparedSnapshot bounds a returned prepared snapshot before encoding.
// The published snapshot carrier declares no embedded materialization document;
// arbitrary payload keys cannot claim the larger document text allowance.
func CheckPreparedSnapshot(snapshot binding.RuntimeSnapshotV1) error {
	projection := transportProjection{limits: value.Runtime(), bytes: 8 << 20}
	return value.ValidateProjected(transportValue{reflect.ValueOf(snapshot), true}, projection.limits, projection.project)
}
