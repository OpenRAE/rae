package planning

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

func TestSnapshotMatchingRefusesMalformedValuesWithoutGrantingUnchanged(t *testing.T) {
	resource := plannedResource{facts: processor.Resource{Address: "provision.node.host", Domain: "provisioning", Kind: "node"}, payload: json.RawMessage(`{"count":1}`)}
	entry := snapshotEntry{Domain: "provisioning", Kind: "node", Payload: json.RawMessage(`{"count":1}`)}
	if matches, err := entryMatches(entry, resource, nil); err != nil || !matches {
		t.Fatalf("identical predecessor refused: %t %v", matches, err)
	}
	for _, raw := range []json.RawMessage{json.RawMessage(`{`), json.RawMessage(`{"count":2}`)} {
		changed := entry
		changed.Payload = raw
		if matches, err := entryMatches(changed, resource, nil); err != nil || matches {
			t.Fatalf("changed predecessor granted unchanged: %t %v", matches, err)
		}
	}
	resource.payload = json.RawMessage(`{`)
	if matches, err := entryMatches(entry, resource, nil); err != nil || matches {
		t.Fatal("malformed requested value granted unchanged")
	}
}

func TestPreparedPresenceRebasesOnlyTheMatchingNativeRuntimeConcern(t *testing.T) {
	selection := preparedSelection{
		concernPaths: map[string][]string{"runtime-dns": {"runtime", "dns"}},
		nodePresence: map[string]map[string][]string{"provision.node.host": {"runtime.dns": {"servers"}, "runtime.dns.servers[0]": {"address"}, "runtime.dns_other": {"private"}, "runtime.mounts": {"target"}}},
	}
	authority := realization.Authority{Address: "provision.node.host", Concern: "runtime-dns"}
	presence, err := selection.preparedOfferPresence(authority, nil)
	want := map[string][]string{"": {"servers"}, "servers[0]": {"address"}}
	if err != nil || !cmp.Equal(presence, want) {
		t.Fatalf("presence escaped its concern: %+v %v", presence, err)
	}
	authority.Address = "provision.node.other"
	if _, err := selection.preparedOfferPresence(authority, nil); err == nil {
		t.Fatal("missing native node identity accepted")
	}
	if _, err := selection.preparedOfferPresence(authority, map[string]any{"name": "other", "spec": map[string]any{"node": false}}); err == nil {
		t.Fatal("malformed native node supplied presence")
	}
	authority.Concern = "os-family"
	if presence, err := selection.preparedOfferPresence(authority, nil); err != nil || presence != nil {
		t.Fatal("non-runtime concern received invented typed presence")
	}
}

func TestDescriptorProfilesRequireCommittedIndependentTargetContext(t *testing.T) {
	owner, err := planOwner()
	if err != nil {
		t.Fatal(err)
	}
	selected := privateServiceProfile(t)
	var context binding.DomainProfileResolutionContextV1
	if err := json.Unmarshal([]byte(`{"namespace_admissions":[],"definitions":[]}`), &context); err != nil {
		t.Fatal(err)
	}
	for _, committed := range []bool{false, true} {
		findings, err := descriptorProfileDiagnostics(owner, []binding.DomainProfileBindingV1{selected}, &context, committed)
		if err != nil || len(findings) != 1 || findings[0].Code != "realization.descriptor-profile-unsupported" {
			t.Fatalf("unpinned descriptor granted authority: %+v %v", findings, err)
		}
	}
	if findings, err := descriptorProfileDiagnostics(owner, nil, nil, false); err != nil || len(findings) != 0 {
		t.Fatal("absent descriptor profiles required target authority")
	}
}
