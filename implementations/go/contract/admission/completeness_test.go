package admission

import "testing"

func TestCompletenessLocalRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"scientific-completeness-taxonomy-rectangular", `{"concerns":[{"concern_id":"a"}],"profiles":[{"profile_id":"p","dispositions":{"a":"required"}}]}`, true},
		{"scientific-completeness-taxonomy-rectangular", `{"concerns":[{"concern_id":"a"}],"profiles":[{"profile_id":"p","dispositions":{"a":"required","b":"excluded"}}]}`, false},
		{"scientific-completeness-taxonomy-rectangular", `{"concerns":[{"concern_id":"a"},{"concern_id":"a"}]}`, false},
		{"scientific-completeness-assessment-status-evidence", `{"concerns":[{"concern_id":"a","status":"implemented","evidence":[{"kind":"implementation","path":"impl/a"}]}]}`, true},
		{"scientific-completeness-assessment-status-evidence", `{"concerns":[{"concern_id":"a","status":"implemented","evidence":[{"kind":"documentation","path":"docs/a"}]}]}`, false},
		{"scientific-completeness-assessment-status-evidence", `{"concerns":[{"concern_id":"a","status":"external-contract","external_contract_refs":["c"],"satisfiability_witness_refs":{"c":"fixtures/a"},"binding_obligation":"resolve c","evidence":[{"kind":"contract","contract_id":"c","path":"contracts/c"}]}]}`, true},
		{"scientific-completeness-assessment-status-evidence", `{"concerns":[{"concern_id":"a","status":"partial"}]}`, false},
		{"scientific-completeness-assessment-status-evidence", `{"concerns":[{"concern_id":"a","status":"partial","issue_refs":["#1"],"evidence":[{"kind":"test","path":"tests/../secret"}]}]}`, false},
		{"scientific-completeness-assessment-status-evidence", `{"concerns":[{"concern_id":"a","status":"missing","issue_refs":["#1"]}]}`, true},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

func TestCompletenessExactTaxonomyJoin(t *testing.T) {
	taxonomy := decodeRuleObject(t, `{"revision":"rev1","concerns":[{"concern_id":"a"}]}`)
	for _, test := range []struct {
		raw   string
		valid bool
	}{
		{`{"taxonomy_revision":"rev1","concerns":[{"concern_id":"a"}]}`, true},
		{`{"taxonomy_revision":"rev2","concerns":[{"concern_id":"a"}]}`, false},
		{`{"taxonomy_revision":"rev1","concerns":[{"concern_id":"a"},{"concern_id":"extra"}]}`, false},
	} {
		if err := assessmentTaxonomy(decodeRuleObject(t, test.raw), taxonomy); (err == nil) != test.valid {
			t.Errorf("assessmentTaxonomy(%s) = %v, want valid=%v", test.raw, err, test.valid)
		}
	}
}
