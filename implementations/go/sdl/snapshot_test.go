package sdl_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestLegacySnapshotAuthenticatesOriginalBeforeMigration(t *testing.T) {
	family, err := sdl.Parse([]byte("name: historical\nnodes:\n  server: {type: compute}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(family, nil)
	if err != nil {
		t.Fatal(err)
	}
	scenario := instance.Document()
	nodes := requireType[map[string]any](t, scenario["nodes"])
	node := requireType[map[string]any](t, nodes["server"])
	node["type"] = "vm"
	delete(node, "architecture")
	scenario["vulnerabilities"] = map[string]any{}
	snapshot := map[string]any{"profile": "raes-sdl-instantiated-snapshot/v2", "scenario": scenario}
	raw := snapshotTestJSON(t, snapshot)
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		t.Fatal(err)
	}
	original := digest.SHA256(canonical)
	migrated, err := sdl.AdmitSnapshotWithContext(t.Context(), raw, original)
	if err != nil {
		t.Fatal(err)
	}
	got := migrated.Document()
	if _, present := got["vulnerabilities"]; present {
		t.Fatal("retired empty container retained")
	}
	provenance := requireType[map[string]any](t, got["instantiation_provenance"])
	constraints := requireType[[]any](t, provenance["realization_constraints"])
	if len(constraints) != 1 {
		t.Fatalf("lost exact VM intent: %v", constraints)
	}
	constraint := requireType[map[string]any](t, constraints[0])
	if constraint["field_pointer"] != "/nodes/server" || constraint["provenance"] != "legacy-node-type-vm" || constraint["posture"] != "exact" {
		t.Fatalf("wrong constraint: %v", constraint)
	}
	if _, err = sdl.AdmitSnapshotWithContext(t.Context(), raw, "sha256:"+strings.Repeat("a", 64)); err == nil {
		t.Fatal("forged historical join admitted")
	}
	if _, err = sdl.ParseWithContext(t.Context(), snapshotTestJSON(t, scenario), sdl.DefaultParseOptions()); err == nil {
		t.Fatal("strict source parsing migrated a legacy snapshot")
	}
}

func snapshotTestJSON(t *testing.T, value any) []byte {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestSnapshotAdmissionRejectsExcessDepthBeforeMigration(t *testing.T) {
	raw := []byte(`{"profile":"raes-sdl-instantiated-snapshot/v2","scenario":{"private":` + strings.Repeat("[", 129) + "0" + strings.Repeat("]", 129) + "}}")
	_, err := sdl.AdmitSnapshotWithContext(t.Context(), raw, "sha256:"+strings.Repeat("a", 64))
	if err == nil || strings.Contains(err.Error(), "private") {
		t.Fatalf("unsafe snapshot admission: %v", err)
	}
}

func TestCurrentSnapshotAdmissionBindsVersionAndRejectsLegacyKinds(t *testing.T) {
	family, err := sdl.Parse([]byte("name: current\nnodes:\n  server: {type: compute}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(family, nil)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := sdl.CanonicalBytes(instance)
	if err != nil {
		t.Fatal(err)
	}
	var snapshot map[string]any
	if err = json.Unmarshal(raw, &snapshot); err != nil {
		t.Fatal(err)
	}
	snapshot["profile"] = "raes-sdl-instantiated-snapshot/v3"
	raw = snapshotTestJSON(t, snapshot)
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = sdl.AdmitSnapshotWithContext(t.Context(), raw, digest.SHA256(canonical)); err != nil {
		t.Fatal(err)
	}
	if _, err = sdl.AdmitSnapshotWithContext(t.Context(), raw, "sha256:"+strings.Repeat("a", 64)); err == nil {
		t.Fatal("forged current digest admitted")
	}
	scenario := requireType[map[string]any](t, snapshot["scenario"])
	nodes := requireType[map[string]any](t, scenario["nodes"])
	requireType[map[string]any](t, nodes["server"])["type"] = "vm"
	raw = snapshotTestJSON(t, snapshot)
	canonical, err = canonjson.JCS(raw)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = sdl.AdmitSnapshotWithContext(t.Context(), raw, digest.SHA256(canonical)); err == nil {
		t.Fatal("v3 label authorized legacy migration")
	}
}
