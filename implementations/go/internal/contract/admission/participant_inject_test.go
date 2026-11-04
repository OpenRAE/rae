package admission

import (
	"encoding/base64"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestParticipantInjectLocalRules(t *testing.T) {
	e := boundTestOwner(t)
	for id, file := range map[string]string{
		"participant-inject-application-local-consistency":      "participant-inject-application-v1",
		"participant-inject-delivery-local-consistency":         "participant-inject-delivery-v1",
		"participant-inject-delivery-receipt-local-consistency": "participant-inject-delivery-receipt-v1",
	} {
		root := fixtureObject(t, "fixtures/control-plane/"+file+"/valid/basic.json")
		rule, ok := e.checker(id)
		if !ok {
			t.Fatalf("missing rule %s", id)
		}
		if err := rule.check(validation.Invocation{Instance: root}); err != nil {
			t.Errorf("%s: %v", id, err)
		}
	}
	for _, test := range []struct {
		name, encoding, content string
		valid                   bool
	}{
		{"exact UTF-8 bound", "utf-8", strings.Repeat("a", 65536), true},
		{"UTF-8 byte overflow", "utf-8", strings.Repeat("é", 32769), false},
		{"exact base64 bound", "base64", base64.StdEncoding.EncodeToString(make([]byte, 65536)), true},
		{"base64 byte overflow", "base64", base64.StdEncoding.EncodeToString(make([]byte, 65537)), false},
		{"base64 line break", "base64", "YWJj\n", false},
		{"reference trailing bits", "base64", "YR==", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := fixtureObject(t, "fixtures/control-plane/participant-inject-delivery-v1/valid/basic.json")
			root["content_encoding"], root["content"] = test.encoding, test.content
			if err := participantInjectContent(root); (err == nil) != test.valid {
				t.Errorf("content boundary = %v, want valid=%v", err, test.valid)
			}
		})
	}
	root := fixtureObject(t, "fixtures/control-plane/participant-inject-delivery-v1/valid/basic.json")
	root["source_snapshot_ref"] = "runtime.snapshot.revision.999"
	if err := participantInjectContent(root); err == nil {
		t.Error("snapshot cut mismatch was accepted")
	}
}
