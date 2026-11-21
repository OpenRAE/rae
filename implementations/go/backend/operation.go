package backend

import (
	"reflect"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// RequireOperationProvider checks explicit opt-in and the installed Go method
// set without invoking foreign code. Effective support remains a separate check.
func RequireOperationProvider(provider any, declaredContracts []string) (OperationProvider, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	if err := admission.CheckBackendContractVersions(declaredContracts); err != nil {
		return nil, err
	}
	profile, err := LoadProfile("operation-supervision")
	if err != nil {
		return nil, err
	}
	required, _ := profile.RequiredContracts.Value()
	for _, contract := range required {
		if strings.HasPrefix(contract, "backend-operation-") && !slices.Contains(declaredContracts, contract) {
			return nil, providerInvalid()
		}
	}
	installed, ok := provider.(OperationProvider)
	if !ok || nilProvider(provider) {
		return nil, providerInvalid()
	}
	return installed, nil
}

// RequireInjectOccurrenceProvider adds the explicit occurrence and outcome opt-in.
func RequireInjectOccurrenceProvider(provider any, declaredContracts []string) (OperationProvider, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	if !slices.Contains(declaredContracts, "inject-occurrence-v1") || !slices.Contains(declaredContracts, "inject-occurrence-outcome-v1") {
		return nil, providerInvalid()
	}
	return RequireOperationProvider(provider, declaredContracts)
}

// RequireMixedService checks one separately negotiated mixed-service role.
func RequireMixedService(service any, role string, declaredContracts []string) error {
	if err := admission.CheckBackendContractVersions(declaredContracts); err != nil {
		return err
	}
	if nilProvider(service) || !slices.Contains(declaredContracts, "mixed-backend-execution-binding-v1") || !slices.Contains(declaredContracts, "mixed-backend-stage-report-v1") {
		return providerInvalid()
	}
	var installed bool
	switch role {
	case "bridge":
		_, installed = service.(MixedBridge)
		if _, err := RequireOperationProvider(service, declaredContracts); err != nil {
			return err
		}
	case "coordinator":
		_, installed = service.(MixedTimeCoordinator)
	case "reader":
		_, installed = service.(MixedStageReader)
	default:
		return providerInvalid()
	}
	if !installed {
		return providerInvalid()
	}
	return nil
}
func providerInvalid() error {
	return fault.New(fault.InvalidInput, "backend-provider-not-installed", nil)
}
func nilProvider(provider any) bool {
	if provider == nil {
		return true
	}
	value := reflect.ValueOf(provider)
	kind := value.Kind()
	if kind == reflect.Pointer || kind == reflect.Interface || kind == reflect.Map || kind == reflect.Slice || kind == reflect.Func || kind == reflect.Chan {
		return value.IsNil()
	}
	return false
}
