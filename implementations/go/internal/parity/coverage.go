package parity

import (
	"errors"
	"fmt"
)

// checkCoverage enforces the implemented inventory independently of the runner
// registry. Complete mode additionally forbids every uncovered corpus key.
func checkCoverage(cases []Case, registered map[string]Runner, implemented []string, complete bool) error {
	keys := map[string]bool{}
	for _, c := range cases {
		keys[c.Key()] = true
	}
	problems := registryProblems(keys, registered, implemented)
	if complete {
		for key := range keys {
			if registered[key] == nil {
				problems = append(problems, fmt.Errorf("cutover requires a runner for %q", key))
			}
		}
	}
	return errors.Join(problems...)
}

func registryProblems(keys map[string]bool, registered map[string]Runner, implemented []string) []error {
	var problems []error
	required := map[string]bool{}
	for _, key := range implemented {
		if required[key] {
			problems = append(problems, fmt.Errorf("duplicate implemented key %q", key))
		}
		required[key] = true
		if registered[key] == nil {
			problems = append(problems, fmt.Errorf("implemented surface %q has no runner", key))
		}
	}
	for key, run := range registered {
		if run == nil || !keys[key] {
			problems = append(problems, fmt.Errorf("runner %q is nil or has no cases", key))
		}
		if !required[key] {
			problems = append(problems, fmt.Errorf("runner %q is missing from the implemented inventory", key))
		}
	}
	return problems
}
