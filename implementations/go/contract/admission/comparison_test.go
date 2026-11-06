package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestComparisonProjectionAndAttackEvidence(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ id, rule, path, field string }{
		{"semantic-comparison-request-v1", "semantic-comparison-governed-scope", "semantic-comparison/semantic-comparison-request-v1/valid/scenario.json", "impact_scope"},
		{"semantic-comparison-result-v1", "semantic-comparison-independent-change-axes", "semantic-comparison/semantic-comparison-result-v1/valid/changed-with-impact.json", "impact_scope_digest"},
		{"semantic-projection-report-v1", "semantic-projection-exact-frame-partition", "concept-authority/semantic-projection-report-v1/valid/declared-attack-enterprise.json", "frame_digest"},
		{"exploit-path-analysis-evidence-v1", "exploit-path-evidence-digest-joins", "exploit-path-analysis/exploit-path-analysis-evidence-v1/valid/valid-path.json", "query_digest"},
	} {
		t.Run(test.id, func(t *testing.T) {
			root := fixtureObject(t, "fixtures/"+test.path)
			rule, ok := e.checker(test.rule)
			if !ok {
				t.Fatal("missing rule", test.rule)
			}
			if err := rule.check(validation.Invocation{Instance: root}); err != nil {
				t.Fatal(err)
			}
			if test.field == "impact_scope" {
				object(root[test.field])["scope_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
			} else {
				root[test.field] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
			}
			if err := rule.check(validation.Invocation{Instance: root}); err == nil {
				t.Error("accepted altered digest")
			}
		})
	}
}
