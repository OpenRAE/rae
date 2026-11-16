package trial

import (
	"context"
	"encoding/json"
	"os"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type testConfigurationOwner struct {
	calls    int
	reject   bool
	collapse bool
}

func (v *testConfigurationOwner) ValidateAndNormalize(_ context.Context, c admission.ParticipantConfiguration) (admission.ParticipantConfiguration, error) {
	v.calls++
	if v.reject {
		return admission.ParticipantConfiguration{}, fault.New(fault.InvalidInput, "configuration-refused", nil)
	}
	if v.collapse {
		for index := range c.Values {
			if c.Values[index].TargetID == "policy.temperature" {
				c.Values[index].Value.Literal = 0.0
			}
		}
	}
	return c, nil
}

func TestCompilerRejectsChangedAdmittedBinding(t *testing.T) {
	request := compilerRequest(t, referenceCompilations(t)[7].Request)
	request.ParticipantConfigurationValidators = map[ConfigurationValidatorKey]admission.ParticipantConfigurationValidator{{ValidatorID: "participant-config", ValidatorVersion: "1"}: &testConfigurationOwner{collapse: true}}
	result, err := Compile(request)
	if err != nil {
		t.Fatal(err)
	}
	if result.Plan != nil || len(result.Diagnostics) != 1 {
		t.Fatal("equal effects produced an admitted comparison", result.Diagnostics)
	}
}
func TestCompilerSelectsConfigurationValidatorByDeclaredOwner(t *testing.T) {
	ref := referenceCompilations(t)[7]
	request := compilerRequest(t, ref.Request)
	owner := &testConfigurationOwner{}
	request.ParticipantConfigurationValidators = map[ConfigurationValidatorKey]admission.ParticipantConfigurationValidator{{ValidatorID: "participant-config", ValidatorVersion: "1"}: owner}
	result, err := Compile(request)
	if err != nil || result.Plan == nil {
		t.Fatal(result.Diagnostics, err)
	}
	if owner.calls != 8 {
		t.Fatal("owner hook calls =", owner.calls, "want 8")
	}
	owner.reject = true
	result, err = Compile(request)
	if err != nil {
		t.Fatal(err)
	}
	if result.Plan != nil || len(result.Diagnostics) != 1 || result.Diagnostics[0].Code != "trial-compiler.participant-configuration-rejected" {
		t.Fatal("owner refusal did not abort plan", result.Diagnostics)
	}
}

func TestCompilerRefusalsMatchIndependentReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/compiler-refusal-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []struct {
			Name    string           `json:"name"`
			Request referenceRequest `json:"request"`
			Codes   []string         `json:"codes"`
		} `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("invalid refusal reference")
	}
	for _, ref := range reference.Cases {
		t.Run(ref.Name, func(t *testing.T) {
			result, err := Compile(compilerRequest(t, ref.Request))
			if err != nil {
				t.Fatal(err)
			}
			codes := []string{}
			for _, diagnostic := range result.Diagnostics {
				codes = append(codes, diagnostic.Code)
			}
			if result.Plan != nil || !slices.Equal(codes, ref.Codes) {
				t.Fatal("refusal differs:", codes, "want", ref.Codes)
			}
		})
	}
}
