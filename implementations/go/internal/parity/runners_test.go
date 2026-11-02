package parity

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestRandstreamVectorRejectsInvalidInputs(t *testing.T) {
	const valid = `{"profile_id":"blake3-xof-v1",` +
		`"root_entropy":{"encoding":"hex-fixed-width","value":"0000000000000000000000000000000000000000000000000000000000000000"},` +
		`"address":{"namespace":"n","trial_coordinate":{},"selection_policy_id":"p","variation_point_id":"v","draw_purpose":"other","local_coordinate":0},` +
		`"transform":{"minimum":0,"maximum":9,"max_rejection_attempts":1}}`
	tests := map[string]string{
		"invalid JSON":          "{",
		"invalid coordinate":    strings.Replace(valid, `"local_coordinate":0`, `"local_coordinate":"zero"`, 1),
		"unsupported encoding":  strings.Replace(valid, "hex-fixed-width", "base64", 1),
		"unsupported profile":   strings.Replace(valid, "blake3-xof-v1", "unknown", 1),
		"inexact coordinate":    strings.Replace(valid, `"local_coordinate":0`, `"local_coordinate":9007199254740992`, 1),
		"invalid dimensions":    strings.Replace(valid, `"trial_coordinate":{}`, `"trial_coordinate":1`, 1),
		"negative coordinate":   strings.Replace(valid, `"local_coordinate":0`, `"local_coordinate":-1`, 1),
		"null minimum":          strings.Replace(valid, `"minimum":0`, `"minimum":null`, 1),
		"null maximum":          strings.Replace(valid, `"maximum":9`, `"maximum":null`, 1),
		"reversed bounds":       strings.Replace(valid, `"minimum":0`, `"minimum":10`, 1),
		"fractional bound":      strings.Replace(valid, `"minimum":0`, `"minimum":0.5`, 1),
		"no rejection attempts": strings.Replace(valid, `"max_rejection_attempts":1`, `"max_rejection_attempts":0`, 1),
	}
	for name, input := range tests {
		t.Run(name, func(t *testing.T) {
			c := Case{Files: map[string][]byte{"vector.json": []byte(input)}}
			if got, err := randstreamVector(t.Context(), c); err == nil {
				t.Errorf("randstreamVector() = %s, %v, want an error", got, err)
			}
		})
	}
}

func TestCanonicalStreamAddressRejectsInvalidJSON(t *testing.T) {
	if got, err := canonicalStreamAddress(json.RawMessage("{")); err == nil {
		t.Errorf("canonicalStreamAddress() = %s, %v, want an error", got, err)
	}
}
