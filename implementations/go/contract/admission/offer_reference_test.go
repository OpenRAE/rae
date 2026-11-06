package admission

import (
	"encoding/json"
	"strconv"
	"testing"
)

func TestOfferProjectionAndSubsetMatchPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Kind       string          `json:"kind"`
			Left       json.RawMessage `json:"left"`
			Right      json.RawMessage `json:"right"`
			Expression json.RawMessage `json:"expression"`
			Node       json.RawMessage `json:"node"`
			Prefix     string          `json:"prefix"`
			Admitted   bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/offer-verdicts.json", &reference)
	if len(reference.Cases) != 1800 {
		t.Fatal("independent offer inventory changed")
	}
	for index, c := range reference.Cases {
		t.Run(c.Kind+"/"+strconv.Itoa(index), func(t *testing.T) {
			var admitted bool
			switch c.Kind {
			case "subset":
				admitted = materializationDomainSubset(decodeRuleObject(t, string(c.Left)), decodeRuleObject(t, string(c.Right)))
			case "projection":
				admitted = materializationOfferIn(decodeRuleObject(t, string(c.Node)), c.Prefix, nil, decodeRuleObject(t, string(c.Expression))) == nil
			default:
				t.Fatal("unknown reference check")
			}
			if admitted != c.Admitted {
				t.Fatalf("offer result=%v Python=%v", admitted, c.Admitted)
			}
		})
	}
}
