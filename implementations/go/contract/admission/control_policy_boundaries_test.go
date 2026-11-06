package admission

import (
	"encoding/json"
	"strconv"
	"testing"
)

func TestControlPolicyOwnerProjectionRefusesMalformedFields(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var reference struct {
		Cases []struct {
			Context struct{ Policies []json.RawMessage }
		}
	}
	readFullReferenceJSON(t, "testdata/control-history-verdicts-01.json", &reference)
	raw := reference.Cases[0].Context.Policies[0]
	if _, err := e.controlPolicy(raw); err != nil {
		t.Fatal("independently admitted policy:", err)
	}
	root := decodeRuleObject(t, string(raw))
	paths := controlPolicyMalformedPaths(root, nil)
	if len(paths) < 20 {
		t.Fatal("missing owner field boundaries")
	}
	for n, path := range paths {
		t.Run(strconv.Itoa(n), func(t *testing.T) {
			v := decodeRuleObject(t, string(raw))
			applyReferenceChange(t, v, referenceChange{Path: path, Value: json.RawMessage(`false`)})
			if _, err := e.controlPolicy(controlJSON(t, v)); err == nil {
				t.Fatal("malformed policy field admitted", path)
			}
		})
	}
	for _, name := range []string{"extra-root", "extra-state", "extra-transition", "duplicate-state", "duplicate-transition", "missing-state", "missing-transition", "initial-state"} {
		t.Run(name, func(t *testing.T) {
			v := decodeRuleObject(t, string(raw))
			states := array(at(v, "states"))
			transitions := array(at(v, "transitions"))
			switch name {
			case "extra-root":
				object(v)["hidden"] = true
			case "extra-state":
				object(states[0])["hidden"] = true
			case "extra-transition":
				object(transitions[0])["hidden"] = true
			case "duplicate-state":
				object(v)["states"] = append(states, states[0])
			case "duplicate-transition":
				object(v)["transitions"] = append(transitions, transitions[0])
			case "missing-state":
				object(v)["states"] = []any{}
			case "missing-transition":
				object(v)["transitions"] = []any{}
			case "initial-state":
				object(v)["initial_state_ref"] = "foreign"
			}
			if _, err := e.controlPolicy(controlJSON(t, v)); err == nil {
				t.Fatal("malformed policy structure admitted")
			}
		})
	}
}

func controlPolicyMalformedPaths(v any, path []string) [][]string {
	result := [][]string{}
	switch v := v.(type) {
	case map[string]any:
		for key, value := range v {
			next := append(append([]string{}, path...), key)
			result = append(result, next)
			result = append(result, controlPolicyMalformedPaths(value, next)...)
		}
	case []any:
		for n, value := range v {
			next := append(append([]string{}, path...), strconv.Itoa(n))
			result = append(result, next)
			result = append(result, controlPolicyMalformedPaths(value, next)...)
		}
	}
	return result
}
