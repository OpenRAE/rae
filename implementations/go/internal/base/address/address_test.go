package address

import (
	"errors"
	"strings"
	"testing"
)

func TestValidAcceptsOnlyCanonicalCompiledAddresses(t *testing.T) {
	segment := "a" + strings.Repeat("b", 63)
	tests := map[string]bool{
		"provision.node.web":               true,
		"a.__private":                      true,
		"x-1.y_2":                          true,
		segment + "." + segment:            true,
		"single":                           false,
		"Upper.case":                       false,
		"a..b":                             false,
		".a.b":                             false,
		"a.b.":                             false,
		"_a.b":                             false,
		"a.b" + segment + "c":              false,
		"a.é":                              false,
		"a.__privat":                       false,
		strings.Repeat("a.", 1023) + "ab":  true,
		strings.Repeat("a.", 1023) + "abc": false,
		strings.Repeat("a.", 1024) + "ab":  false,
	}
	for input, want := range tests {
		if got := Valid(input); got != want {
			t.Errorf("Valid(%q) = %t, want %t", input, got, want)
		}
	}
}

func TestRenderSkipsEmptyPartsAndChecksTheResult(t *testing.T) {
	got, err := Render("provision", "", "node", "web")
	if err != nil || got != "provision.node.web" {
		t.Errorf("Render() = %q, %v, want provision.node.web", got, err)
	}
	if _, err := Render("only"); !errors.Is(err, ErrAddress) {
		t.Errorf("Render(only) error = %v, want ErrAddress", err)
	}
}

func TestPlanRootNamesTheRootOfEachPlanDomain(t *testing.T) {
	for domain, want := range map[string]string{"provisioning": "provision", "orchestration": "orchestration", "evaluation": "evaluation"} {
		if got, ok := PlanRoot(domain); !ok || got != want {
			t.Errorf("PlanRoot(%q) = %q, %t, want %q", domain, got, ok, want)
		}
	}
	if _, ok := PlanRoot("runtime"); ok {
		t.Error("PlanRoot(runtime) ok = true, want false")
	}
}

func TestCompilerOwnedTemporalSubject(t *testing.T) {
	tests := map[string]bool{
		"sdl.x": true,
		"participant.behavior-specification.b.inject-delivery.d": true,
		"participant.behavior-specification..inject-delivery.d":  false,
		"participant.behavior-specification.b.inject-delivery.":  false,
		"participant.behavior-specification.b.other.d":           false,
		"participant.behavior-specification.b.inject-delivery":   false,
		"runtime.x": false,
	}
	for input, want := range tests {
		if got := CompilerOwnedTemporalSubject(input); got != want {
			t.Errorf("CompilerOwnedTemporalSubject(%q) = %t, want %t", input, got, want)
		}
	}
}
