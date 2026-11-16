package admission

import (
	"context"
	"math"
	"math/big"
	"strings"
	"testing"
)

func TestConfigurationBudgetsRefuseNonfiniteAndUnboundedNativeNumbers(t *testing.T) {
	for _, number := range []any{math.Inf(1), new(big.Int).Lsh(big.NewInt(1), (8*1048576)+1)} {
		configuration := ParticipantConfiguration{Values: []RealizedConfigurationValue{{TargetID: "number", ValueType: "number", Origin: "override", Value: BindingValue{Kind: "literal", Literal: number}}}}
		for _, check := range []func() error{
			func() error { _, err := configurationDocument(configuration); return err },
			func() error { return configurationBudget(configuration) },
			func() error { return configurationRequestBudget(ParticipantConfigurationRequest{}, configuration) },
		} {
			if err := check(); err == nil {
				t.Fatal("unsupported native number entered configuration construction")
			}
		}
	}
}
func TestControlContextOwnerPanicsRemainSanitized(t *testing.T) {
	owner := configurationContextCheck(func(context.Context, string, ControlContextSelection) error { panic("private control-context panic") })
	if err := checkConfigurationContext(t.Context(), owner, "participant", ControlContextSelection{}); err == nil || strings.Contains(err.Error(), "private") {
		t.Fatal("control owner panic escaped", err)
	}
}
