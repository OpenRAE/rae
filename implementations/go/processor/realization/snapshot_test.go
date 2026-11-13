package realization

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestSnapshotSanitizerKeepsStatefulMountsAndSafeValues(t *testing.T) {
	var snapshot binding.RuntimeSnapshotV1
	raw := []byte(`{"entries":{"provision.node.server":{"address":"provision.node.server","domain":"provisioning","resource_type":"node","payload":{"spec":{"node":{"runtime":{"environment":[{"name":"PUBLIC","value":"example"}],"mounts":[{"target":"/volume","source_kind":"volume","source":"stored"},{"target":"/data","source_kind":"bind","source":"/data"}]}}}}}}}`)
	if err := json.Unmarshal(raw, &snapshot); err != nil {
		t.Fatal(err)
	}
	requirements := []Requirement{{Address: "provision.node.server", Kind: "runtime-environment"}, {Address: "provision.node.server", Kind: "runtime-mounts"}}
	sanitized, err := SanitizeSnapshot(requirements, snapshot)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(sanitized)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(encoded, []byte(`"value":"example"`)) || !bytes.Contains(encoded, []byte(`"source_kind":"volume"`)) || !bytes.Contains(encoded, []byte(`"value_commitment"`)) {
		t.Fatalf("unsafe or incomplete sanitized snapshot: %s", encoded)
	}
	original := requireJSON(t, snapshot)
	if !bytes.Contains(original, []byte(`"value":"example"`)) {
		t.Fatal("sanitization mutated the caller's snapshot")
	}
}

func TestEquivalentRepairsMalformedLegacyObservation(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	value := func(raw string) admission.Fragment {
		t.Helper()
		document, checkErr := nativeValue([]byte(raw))
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		fragment, checkErr := admission.AdmitFragment(owner, admission.RealizationValue, document, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		return fragment
	}
	before := value(`{"spec":{"node":{"runtime":{"environment":[{"name":"PUBLIC","value":"example"}]}}}}`)
	malformed := value(`{"spec":{"node":{"runtime":{"environment":[{"name":"PUBLIC","value_present":true}]}}}}`)
	requirements := []Requirement{{Address: "provision.node.server", Kind: "runtime-environment"}}
	equal, err := Equivalent(requirements, "provision.node.server", before, before)
	if err != nil || !equal {
		t.Fatalf("equal payload refused: %v %v", equal, err)
	}
	equal, err = Equivalent(requirements, "provision.node.server", before, malformed)
	if err != nil || equal {
		t.Fatalf("malformed legacy payload was not a recoverable mismatch: %v %v", equal, err)
	}
}
