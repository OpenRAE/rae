package admission

import (
	"encoding/base64"
	"encoding/json"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) participantInjectRules() map[string]definition {
	return map[string]definition{
		// This local carrier has only the published closed type and bound rules.
		// Its reference model supplies no runtime authority or additional join.
		"participant-inject-application-local-consistency": {check: func(i validation.Invocation) error {
			return e.schemaInstance("participant-inject-application-v1", i.Instance)
		}},
		"participant-inject-delivery-local-consistency": {check: func(i validation.Invocation) error { return participantInjectContent(i.Instance) }},
		"participant-inject-delivery-receipt-local-consistency": {check: func(i validation.Invocation) error {
			if equal(at(i.Instance, "operation_id"), at(i.Instance, termDelivery, "application", "world_operation_id")) {
				return invalid()
			}
			return participantInjectContent(at(i.Instance, termDelivery))
		}},
	}
}
func (e *Validator) schemaInstance(id string, instance any) error {
	raw, err := json.Marshal(instance)
	if err != nil {
		return invalid()
	}
	return e.low.CheckSchema(id, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
}
func participantInjectContent(v any) error {
	if !matchingFields(v, at(v, "application"), fieldParticipantAddress, fieldEpisodeID) {
		return invalid()
	}
	revision, ok := number(at(v, "application", "expected_snapshot_revision"))
	if !ok || !revision.IsInt() || revision.Sign() < 0 || stringAt(v, "source_snapshot_ref") != "runtime.snapshot.revision."+revision.Num().String() {
		return invalid()
	}
	content := stringAt(v, "content")
	if text(defaultMember(v, "content_encoding", "utf-8")) == "utf-8" {
		return require(utf8.ValidString(content) && len(content) <= 65536)
	}
	for _, char := range content {
		if !base64Character(char) {
			return invalid()
		}
	}
	decoded, err := base64.StdEncoding.DecodeString(content)
	return require(err == nil && len(decoded) <= 65536)
}
func base64Character(char rune) bool {
	return char >= 'a' && char <= 'z' || char >= 'A' && char <= 'Z' || char >= '0' && char <= '9' || char == '+' || char == '/' || char == '='
}
