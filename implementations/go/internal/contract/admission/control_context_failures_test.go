package admission

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestControlDisclosureRefusesSubstitutedAuthoritySources(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	for _, name := range []string{"scope", "run", "participant", "episode", "audience", "generation", "generation-fraction", "cut-json", "cut-kind", "cut-shape", "asset-json", "selection-json", "surface-json", "view-json", "duplicate-asset", "duplicate-selection", "duplicate-surface", "duplicate-view", "missing-original", "original-disposition", "original-identity", "record-identity", "missing-surface", "invisible-item", "missing-binding", "duplicate-binding", "binding-source", "missing-view", "view-source", "view-transformation", "inactive-exposure", "denied", "unavailable", "withheld-no-authority"} {
		t.Run(name, func(t *testing.T) {
			v, c, surface, view, binding := controlDisclosureFixture(t)
			corruptControlSnapshot(name, c)
			switch name {
			case "asset-json":
				c.assets = [][]byte{[]byte("{")}
			case "selection-json":
				c.selections = [][]byte{[]byte("{")}
			case "surface-json":
				c.surfaces = [][]byte{[]byte("{")}
			case "view-json":
				c.views = [][]byte{[]byte("{")}
			case "duplicate-asset":
				c.assets = append(c.assets, c.assets[0])
			case "duplicate-selection":
				c.selections = append(c.selections, c.selections[0])
			case "duplicate-surface":
				c.surfaces = append(c.surfaces, c.surfaces[0])
			case "duplicate-view":
				c.views = append(c.views, c.views[0])
			case "missing-original":
				c.selections = nil
			case "original-disposition":
				original := decodeRuleObject(t, string(c.selections[0]))
				object(original)["disposition"] = "withheld"
				c.selections = [][]byte{controlJSON(t, original)}
			case "original-identity":
				original := decodeRuleObject(t, string(c.selections[0]))
				object(original)["selected_by_ref"] = "other"
				c.selections = [][]byte{controlJSON(t, original)}
			case "record-identity":
				v["record_id"] = stringAt(decodeRuleObject(t, string(c.selections[0])), "record_id")
			case "missing-surface":
				c.surfaces = nil
			case "invisible-item":
				object(surface["participant_view"])["visible_context_refs"] = []any{}
			case "missing-binding":
				object(surface["assurance"])["exposure_bindings"] = []any{}
			case "duplicate-binding":
				object(surface["assurance"])["exposure_bindings"] = []any{binding, binding}
			case "binding-source":
				binding["source_ref"] = "urn:sha256:foreign"
			case "missing-view":
				c.views = nil
			case "view-source":
				object(array(view["source_layers"])[0])["source_id"] = "foreign"
			case "view-transformation":
				object(view["transformation"])["transformation_rule_ref"] = "foreign"
			case "inactive-exposure":
				c.snapshot.Lifecycle[[3]string{"privacy-instruction", "one", "cuts.2"}] = "withdrawn"
			case "denied":
				c.allow = false
			case "unavailable":
				c.failure = errors.New("private-owner-failure")
			case "withheld-no-authority":
				v["disposition"] = "withheld"
				delete(v, "withholding_authority_ref")
			}
			if name == "invisible-item" || name == "missing-binding" || name == "duplicate-binding" || name == "binding-source" {
				c.surfaces = [][]byte{controlJSON(t, surface)}
			}
			if name == "view-source" || name == "view-transformation" {
				c.views = [][]byte{controlJSON(t, view)}
			}
			err := e.controlContextAgreement(validation.Invocation{Key: validation.Key{ContractID: "participant-control-context-record-v1"}, Instance: v, Context: c})
			if err == nil {
				t.Fatal("accepted substituted control authority", name)
			}
		})
	}
}

func corruptControlSnapshot(name string, c *controlAgreementTestContext) {
	switch name {
	case "scope":
		c.snapshot.ScopeRef = ""
	case "run":
		c.snapshot.RunID = ""
	case "participant":
		c.snapshot.ParticipantAddress = ""
	case "episode":
		c.snapshot.EpisodeID = ""
	case "audience":
		c.snapshot.AudienceScopeRef = ""
	case "generation":
		c.snapshot.EpisodeGeneration = json.Number("-1")
	case "generation-fraction":
		c.snapshot.EpisodeGeneration = json.Number("0.5")
	case "cut-json":
		c.snapshot.RecordCut = []byte("{")
	case "cut-kind":
		c.snapshot.RecordCut = []byte(`{"cut_kind":"unknown"}`)
	case "cut-shape":
		c.snapshot.RecordCut = []byte(`{"cut_kind":"sequence_prefix"}`)
	}
}
