package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestPinnedVocabularySourceIdentitiesAndOrder(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	for _, test := range []struct{ id, file, rows string }{
		{"attack-enterprise-tactics-source-v1", "attack-enterprise-tactics-source-v1.json", "tactics"},
		{"atlas-tactics-source-v1", "atlas-tactics-source-v1.json", "tactics"},
		{"nist-csf-defensive-categories-source-v1", "nist-csf-defensive-categories-source-v1.json", "categories"},
		{"w3c-activitystreams-activity-types-source-v1", "w3c-activitystreams-activity-types-source-v1.json", "activity_types"},
		{"fipa-communicative-acts-source-v1", "fipa-communicative-acts-source-v1.json", "communicative_acts"},
	} {
		t.Run(test.id, func(t *testing.T) {
			v := fixtureObject(t, "concept-authority/"+test.file)
			if _, err := e.Validate(test.id, controlJSON(t, v), limits, nil); err != nil {
				t.Fatal(err)
			}
			items := array(v[test.rows])
			v[test.rows] = append(items, items[0])
			if _, err := e.Validate(test.id, controlJSON(t, v), limits, nil); err == nil {
				t.Fatal("accepted duplicate source identity")
			}
			if test.id == "atlas-tactics-source-v1" || test.id == "fipa-communicative-acts-source-v1" || test.id == "w3c-activitystreams-activity-types-source-v1" {
				v = fixtureObject(t, "concept-authority/"+test.file)
				items = array(v[test.rows])
				items[0], items[1] = items[1], items[0]
				if _, err := e.Validate(test.id, controlJSON(t, v), limits, nil); err == nil {
					t.Fatal("accepted changed source order")
				}
			}
		})
	}
}
