package processor

import (
	"encoding/json"
	"testing"
)

func TestResourceKindDiagnosticKeepsReferenceFieldOrderAndURIQuotes(t *testing.T) {
	// Pydantic's coordinate display chooses double quotes around this valid URI.
	raw := []byte(`{"namespace":"com.example.private","authority":"urn:example:profiles:it's","profile_id":"packet-counter","revision":"1.0.0","definition_digest":"sha256:0992f3543a26f9ee724c5b8c657ed9839b87db7b139515ad17538073452fbedc"}`)
	var kind participantResourceKind
	if err := json.Unmarshal(raw, &kind); err != nil {
		t.Fatal(err)
	}
	want := `namespace='com.example.private' authority="urn:example:profiles:it's" profile_id='packet-counter' revision='1.0.0' definition_digest='sha256:0992f3543a26f9ee724c5b8c657ed9839b87db7b139515ad17538073452fbedc'`
	if got := kind.label(); got != want {
		t.Fatalf("coordinate display=%s want=%s", got, want)
	}
}
