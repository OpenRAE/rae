package admission

import (
	"slices"
	"strings"
	"testing"
)

func TestExecutionPolicyQueriesRefuseUnboundedAndNoncanonicalScope(t *testing.T) {
	owner := boundTestOwner(t)
	for _, test := range []struct {
		scope     string
		namespace []string
	}{
		{"relative", nil}, {"/" + strings.Repeat("a", 16385), nil}, {"/nodes", make([]string, 32)}, {"/nodes", []string{"invalid/name"}},
	} {
		if _, err := ResolveExecutionPolicy(owner, nil, test.scope, test.namespace, nil); err == nil {
			t.Fatal("invalid execution-policy query accepted")
		}
	}
	if _, err := ResolveExecutionPolicy(nil, nil, "/nodes", nil, nil); err == nil {
		t.Fatal("missing policy validator accepted")
	}
	if result, err := ResolveExecutionPolicy(owner, nil, "/nodes", nil, nil); err != nil || result != nil {
		t.Fatal("absent policy invented execution authority")
	}
	wrong := constraintTestValue(t, owner, `{}`)
	if _, err := ResolveExecutionPolicy(owner, wrong, "/nodes", nil, nil); err == nil {
		t.Fatal("generic value became execution-policy authority")
	}
}

func TestResolvedPolicyCapabilityGapsKeepAuthorityAndSupportSeparate(t *testing.T) {
	owner := boundTestOwner(t)
	for _, test := range []struct {
		policy, support, want string
	}{
		{`{"policy_id":"test","response":"terminate"}`, `{"responses":["terminate"]}`, ""},
		{`{"policy_id":"test","response":"terminate"}`, `{"responses":["retry"]}`, "response-unsupported"},
	} {
		document := constraintTestFragment(t, owner, OperationPolicyDocument, `{"default":`+test.policy+`}`)
		evidence := map[string]Fragment{"e": constraintTestValue(t, owner, `{}`)}
		effective, err := ResolveExecutionPolicy(owner, document, "/workflows/main/steps/run", nil, evidence)
		if err != nil {
			t.Fatalf("policy %s failed: %v", test.policy, err)
		}
		if stringAt(effective.Document(), "retry_unit") != "workflow-step" {
			t.Fatal("workflow policy lost its retry unit")
		}
		support := constraintTestFragment(t, owner, OperationPolicyCapabilities, test.support)
		gaps, err := ExecutionPolicyCapabilityGaps(effective, support)
		want := []string{}
		if test.want != "" {
			want = append(want, test.want)
		}
		if err != nil || !slices.Equal(gaps, want) {
			t.Fatalf("policy support gap changed: %v %v", gaps, err)
		}
	}
}
