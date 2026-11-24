package admission

import (
	"reflect"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// CheckPreparationOperations bounds the complete selected operation list under
// the portable runtime budget and each payload under the realization budget.
// It invokes no supplied methods and grants no schema, identity, or execution admission.
func CheckPreparationOperations(plan binding.ProvisioningPlanV1) error {
	operations, _ := plan.Operations.Value()
	if len(operations) > value.Runtime().MaxMembers {
		return value.ErrLimit
	}
	aggregate := transportProjection{limits: value.Runtime(), bytes: 8 << 20}
	if err := value.ValidateProjected(transportValue{reflect.ValueOf(operations), true}, aggregate.limits, aggregate.project); err != nil {
		return err
	}
	for _, operation := range operations {
		payload, _ := operation.Payload.Value()
		individual := transportProjection{limits: value.Default(), bytes: 8 << 20}
		if err := value.ValidateProjected(transportValue{reflect.ValueOf(payload), true}, individual.limits, individual.project); err != nil {
			return err
		}
	}
	return nil
}
