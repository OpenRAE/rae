package realization

import (
	"encoding/json"
	"testing"
)

func plannedProcessFixture() map[string]any {
	return map[string]any{"resource": "open_file_descriptors", "subject": map[string]any{"name": "worker"}, "scope": "process", "soft": json.Number("32"), "hard": json.Number("64")}
}

func TestPlannedProcessRequirementsRecoverIdentityAndFiniteBounds(t *testing.T) {
	row := plannedProcessFixture()
	expected, err := nativeProcessDemand(row)
	if err != nil {
		t.Fatal(err)
	}
	state := evaluationState{operations: map[string]evaluatedOperation{"provision.node.host": {Payload: map[string]any{"limits": []any{row}}}}}
	authority := plannedAuthority{Address: "provision.node.host", Pointer: "/limits", Kind: termProcessResourceLimits, Mode: termExact, Bounds: []plannedBound{{Identity: expected.IdentityDigest, Pointer: "/soft", Domain: json.RawMessage(`{"kind":"enum","values":[32,48]}`)}}}
	requirement := Requirement{Kind: termProcessResourceLimits}
	if err := state.plannedProcessDemands(authority, &requirement); err != nil {
		t.Fatal(err)
	}
	if len(requirement.ProcessResourceLimits) != 1 || len(requirement.ValueConstraints) != 1 {
		t.Fatalf("missing process authority: %+v", requirement)
	}
	demand := requirement.ProcessResourceLimits[0]
	if demand.IdentityDigest != expected.IdentityDigest || demand.Resource != "open_file_descriptors" || demand.Scope != "process" || demand.Soft.Document() != json.Number("32") || demand.Hard.Document() != json.Number("64") {
		t.Fatalf("changed process identity or bounds: %+v", demand)
	}
	bound := requirement.ValueConstraints[0]
	allowed, ok := bound.AllowedValues.Document().([]any)
	if !ok || bound.IdentityDigest != demand.IdentityDigest || bound.Leaf != "soft" || len(allowed) != 2 {
		t.Fatalf("lost finite process bound: %+v", bound)
	}
	for _, domain := range []json.RawMessage{json.RawMessage(`{`), json.RawMessage(`[]`), json.RawMessage(`{"kind":"other"}`)} {
		authority.Bounds[0].Domain = domain
		if err := plannedProcessBounds(authority, &Requirement{}, map[string]bool{expected.IdentityDigest: true}); err == nil {
			t.Fatalf("invalid process domain admitted: %s", domain)
		}
	}
	authority.Bounds[0].Domain = json.RawMessage(`{"kind":"enum","values":[32]}`)
	if plannedProcessBounds(authority, &Requirement{}, map[string]bool{}) == nil {
		t.Fatal("bound attached to absent process identity")
	}
}

func TestPlannedProcessDemandsRefuseMissingAndMalformedValues(t *testing.T) {
	for _, test := range []struct {
		name, mode string
		payload    map[string]any
		wantError  bool
	}{
		{"missing open", termOpen, nil, false},
		{"missing exact", termExact, nil, true},
		{"wrong collection", termExact, map[string]any{"limits": "not-a-list"}, true},
		{"wrong record", termExact, map[string]any{"limits": []any{"not-a-record"}}, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			s := evaluationState{operations: map[string]evaluatedOperation{"provision.node.host": {Payload: test.payload}}}
			r := Requirement{Kind: termProcessResourceLimits}
			err := s.plannedProcessDemands(plannedAuthority{Address: "provision.node.host", Pointer: "/limits", Mode: test.mode}, &r)
			if (err != nil) != test.wantError {
				t.Fatalf("process demand error=%v, expected refusal=%t", err, test.wantError)
			}
		})
	}
	for _, field := range []string{"subject", "soft", "hard"} {
		row := plannedProcessFixture()
		row[field] = func() {}
		if _, err := plannedProcessDemand(row); err == nil {
			t.Fatalf("non-JSON %s admitted", field)
		}
	}
	if preparedProcessDemands(&Requirement{}, "not-a-list") == nil {
		t.Fatal("prepared scalar process list accepted")
	}
	if preparedProcessDemands(&Requirement{}, []any{map[string]any{}}) == nil {
		t.Fatal("incomplete prepared process demand accepted")
	}
	r := Requirement{}
	if err := preparedProcessDemands(&r, []any{plannedProcessFixture()}); err != nil || len(r.ProcessResourceLimits) != 1 {
		t.Fatalf("prepared demand not retained: %+v %v", r, err)
	}
}

func TestCompilerProcessDomainsKeepLeafIdentityAndParameterOrigins(t *testing.T) {
	source := realizationSource{constraints: map[string]capabilityConstraint{
		"/limits/0/soft": {Parameter: []string{"soft_limit"}, Values: []json.RawMessage{json.RawMessage(`32`), json.RawMessage(`48`)}},
		"/limits/0/hard": {Parameter: []string{"hard_limit"}, Values: []json.RawMessage{json.RawMessage(`64`)}},
		"/os":            {Values: []json.RawMessage{json.RawMessage(`"linux"`), json.RawMessage(`"windows"`)}},
	}}
	r := Requirement{Kind: termProcessResourceLimits}
	if err := source.compileBounds(&r, "/limits", []any{plannedProcessFixture()}); err != nil {
		t.Fatal(err)
	}
	if len(r.ProcessResourceLimits) != 1 || len(r.ValueConstraints) != 2 || r.ValueConstraints[0].Parameter[0] != "soft_limit" || r.ValueConstraints[1].Parameter[0] != "hard_limit" {
		t.Fatalf("compiler lost process domains: %+v", r)
	}
	os := Requirement{Kind: termOsFamily}
	if err := source.compileBounds(&os, "/os", "linux"); err != nil || os.ValueDomain == nil || os.ConstraintProvenance != "variable-allowed-values" {
		t.Fatalf("OS domain lost: %+v %v", os, err)
	}
	source.constraints["/os"] = capabilityConstraint{Values: []json.RawMessage{json.RawMessage(`{`)}}
	if source.compileBounds(&os, "/os", "linux") == nil {
		t.Fatal("invalid serialized OS domain accepted")
	}
	source.constraints["/limits/0/soft"] = capabilityConstraint{Values: []json.RawMessage{json.RawMessage(`{`)}}
	if source.compileProcessLeafBounds(&r, "/limits", 0, "id") == nil {
		t.Fatal("invalid serialized process domain accepted")
	}
	if source.compileProcessLimits(&r, "/limits", []any{map[string]any{}}) == nil {
		t.Fatal("invalid source process limit accepted")
	}
}
