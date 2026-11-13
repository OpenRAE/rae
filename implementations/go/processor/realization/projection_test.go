package realization

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type replacedValue struct{ admission.Fragment }

func (replacedValue) Document() any { panic("foreign value called") }

func TestConcernProjectionRefusesForeignValues(t *testing.T) {
	for _, value := range []admission.Fragment{nil, replacedValue{}} {
		if _, err := ProjectConcern("runtime-environment", value, true, false); err == nil {
			t.Fatal("foreign value accepted")
		}
	}
}

func TestEnvironmentProjectionProtectsValuesAndKeepsOccurrenceOrder(t *testing.T) {
	validator, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	value := func(raw any) admission.Fragment {
		t.Helper()
		fragment, checkErr := admission.AdmitFragment(validator, admission.RealizationValue, raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		return fragment
	}
	input := value([]any{map[string]any{"name": "Z", "value": "example", "value_classification": "plain"}, map[string]any{"name": "A", "value": "", "value_classification": "redacted"}})
	projected, err := ProjectConcern("runtime-environment", input, false, false)
	if err != nil {
		t.Fatal(err)
	}
	entries := requireType[[]any](t, projected.Document())
	first, second := requireType[map[string]any](t, entries[0]), requireType[map[string]any](t, entries[1])
	if first["name"] != "A" || first["value_present"] != true || second["value"] != nil || !strings.HasPrefix(requireType[string](t, second["value_commitment"]), "raes-runtime-value-jcs-sha256-v1:sha256:") {
		t.Fatalf("unsafe or unsorted projection: %#v", entries)
	}
	recursive, err := ProjectConcern("runtime-environment", input, false, true)
	if err != nil || requireType[map[string]any](t, requireType[[]any](t, recursive.Document())[0])["name"] != "Z" {
		t.Fatalf("lost source occurrence order: %v", err)
	}
	for _, raw := range []any{
		[]any{map[string]any{"name": "TOKEN", "value": "secret", "value_classification": "redacted"}},
		[]any{map[string]any{"name": "TOKEN", "value": "secret", "value_classification": "secret_fixture"}},
		[]any{map[string]any{"name": "TOKEN", "value": "", "value_commitment": "invalid"}},
		[]any{map[string]any{"name": "TOKEN", "value_from": map[string]any{"generated_artifact": "token", "output": "value", "extra": true}}},
		[]any{map[string]any{"name": "TOKEN", "value_classification": "redacted", "provenance": "runtime", "source": "", "value_present": false}},
		[]any{map[string]any{"name": "TOKEN", "value_classification": "redacted", "provenance": "runtime", "source": "", "value_present": true, "extra": true}},
	} {
		if _, err := ProjectConcern("runtime-environment", value(raw), true, false); err == nil {
			t.Fatal("unsafe observed value was accepted")
		}
	}
}

func TestMountProjectionPreservesPresenceAndSourceOccurrences(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	input, err := admission.AdmitFragment(owner, admission.RealizationValue, []any{
		map[string]any{"target": "/z", "source_kind": "bind", "source": "", "source_sensitivity": "redacted", "options": []any{"z", "a"}},
		map[string]any{"target": "/volume", "source_kind": "volume", "source": "stored"},
		map[string]any{"target": "/a", "source_kind": "tmpfs"},
	}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	result, err := ProjectConcern("runtime-mounts", input, false, false)
	if err != nil {
		t.Fatal(err)
	}
	rows := requireType[[]any](t, result.Document())
	if len(rows) != 2 || requireType[map[string]any](t, rows[0])["target"] != "/a" || requireType[map[string]any](t, rows[1])["source_present"] != true {
		t.Fatalf("wrong mount comparison: %#v", rows)
	}
	recursive, err := ProjectConcern("runtime-mounts", input, false, true)
	if err != nil {
		t.Fatal(err)
	}
	first := requireType[map[string]any](t, requireType[[]any](t, recursive.Document())[0])
	if first["target"] != "/z" || requireType[map[string]any](t, requireType[[]any](t, first["options"])[0])["_identity"] != "z" {
		t.Fatalf("lost source occurrences: %#v", first)
	}
}

func TestObservedMountsAndPortsKeepClosedShapes(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	fragment := func(value any) admission.Fragment {
		t.Helper()
		result, checkErr := admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		return result
	}
	ports := []any{map[string]any{"host_port": json.Number("80"), "container_port": json.Number("80")}, map[string]any{"host_port": json.Number("100"), "container_port": json.Number("80")}}
	projected, err := ProjectConcern("published-ports", fragment(ports), true, false)
	if err != nil {
		t.Fatal(err)
	}
	if requireType[map[string]any](t, requireType[[]any](t, projected.Document())[0])["host_port"] != json.Number("100") {
		t.Fatal("port comparison changed lexical order")
	}
	recursive, err := ProjectConcern("published-ports", fragment(ports), true, true)
	if err != nil || requireType[map[string]any](t, requireType[[]any](t, recursive.Document())[0])["host_port"] != json.Number("80") {
		t.Fatalf("port occurrence order lost: %v", err)
	}
	mount := map[string]any{"target": "/data", "source_kind": "bind", "source": "", "source_sensitivity": "redacted"}
	safe, err := ProjectConcern("runtime-mounts", fragment([]any{mount}), false, false)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ProjectConcern("runtime-mounts", safe, true, false); err != nil {
		t.Fatal(err)
	}
	row := requireType[map[string]any](t, requireType[[]any](t, safe.Document())[0])
	row["source_present"] = false
	if _, err := ProjectConcern("runtime-mounts", fragment([]any{row}), true, false); err == nil {
		t.Fatal("contradictory mount presence accepted")
	}
}

func TestProcessProjectionKeepsSemanticIdentityAndRedaction(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	fragment := func(value any) admission.Fragment {
		t.Helper()
		result, checkErr := admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		return result
	}
	limit := map[string]any{"resource": "open_file_descriptors", "subject": map[string]any{"pid": json.Number("7"), "name": "daemon"}, "soft": json.Number("1024"), "hard": json.Number("4096"), "description": "annotation"}
	first, err := ProjectConcern("process-resource-limits", fragment([]any{limit}), true, true)
	if err != nil {
		t.Fatal(err)
	}
	limit["soft"] = json.Number("2048")
	second, err := ProjectConcern("process-resource-limits", fragment([]any{limit}), true, true)
	if err != nil {
		t.Fatal(err)
	}
	one, two := requireType[map[string]any](t, requireType[[]any](t, first.Document())[0]), requireType[map[string]any](t, requireType[[]any](t, second.Document())[0])
	if one["_identity"] != two["_identity"] || one["description"] != nil || one["soft"] == two["soft"] {
		t.Fatalf("limit identity changed with its leaf: %#v %#v", one, two)
	}
	policy := map[string]any{"required": []any{"CAP_NET_ADMIN", "CAP_CHOWN"}, "process_overrides": []any{map[string]any{"subject": map[string]any{"name": "daemon", "command": []any{"private-argument"}, "command_redacted": true}, "effective": []any{"CAP_CHOWN"}}}}
	projected, err := ProjectConcern("linux-capabilities", fragment(policy), true, true)
	if err != nil {
		t.Fatal(err)
	}
	output := requireType[map[string]any](t, projected.Document())
	override := requireType[map[string]any](t, requireType[[]any](t, output["process_overrides"])[0])
	if len(requireType[[]any](t, requireType[map[string]any](t, override["subject"])["command"])) != 0 || override["_identity"] == nil || requireType[map[string]any](t, requireType[[]any](t, output["required"])[0])["_identity"] != "CAP_NET_ADMIN" {
		t.Fatalf("unsafe capability projection: %#v", output)
	}
}

func TestForwardingAndListenerProjectionKeepDisclosureAndPresence(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	fragment := func(value any) admission.Fragment {
		t.Helper()
		result, checkErr := admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		return result
	}
	input := []any{map[string]any{"forwarding_agent_id": "forwarder", "ownership_role": "author", "settings": []any{map[string]any{"setting_id": "z", "value": "public"}, map[string]any{"setting_id": "a", "value": "", "classification": "redacted"}}}}
	projected, err := ProjectConcern("forwarding-agents", fragment(input), false, false)
	if err != nil {
		t.Fatal(err)
	}
	agent := requireType[map[string]any](t, requireType[[]any](t, projected.Document())[0])
	settings := requireType[[]any](t, agent["settings"])
	if agent["ownership_role"] != nil || requireType[map[string]any](t, settings[0])["setting_id"] != "a" || requireType[map[string]any](t, settings[1])["value"] != nil {
		t.Fatalf("unsafe forwarding projection: %#v", agent)
	}
	recursive, err := ProjectConcern("forwarding-agents", fragment(input), false, true)
	if err != nil || requireType[map[string]any](t, requireType[[]any](t, requireType[map[string]any](t, requireType[[]any](t, recursive.Document())[0])["settings"])[0])["setting_id"] != "z" {
		t.Fatalf("forwarding occurrence order lost: %v", err)
	}
	listeners := []any{map[string]any{"service_listener_id": "partial", "description": "annotation"}}
	result, err := ProjectConcern("service-listeners", fragment(listeners), true, false)
	if err != nil {
		t.Fatal(err)
	}
	row := requireType[map[string]any](t, requireType[[]any](t, result.Document())[0])
	if len(row) != 1 || row["service_listener_id"] != "partial" {
		t.Fatalf("listener defaults became supplied facts: %#v", row)
	}
}

func TestTypedConcernUsesOwnerAndPreservesRecursiveOrder(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	input, err := admission.AdmitFragment(owner, admission.RealizationValue, []any{map[string]any{"name": "z", "description": "annotation"}, map[string]any{"name": "a"}}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	compared, err := ProjectConcern("runtime-processes", input, false, false)
	if err != nil {
		t.Fatal(err)
	}
	rows := requireType[[]any](t, compared.Document())
	if requireType[map[string]any](t, rows[0])["name"] != "a" || requireType[map[string]any](t, rows[0])["description"] != nil || requireType[map[string]any](t, rows[0])["role"] != "other" {
		t.Fatalf("lost owner defaults or comparison rules: %#v", rows)
	}
	recursive, err := ProjectConcern("runtime-processes", input, false, true)
	if err != nil || requireType[map[string]any](t, requireType[[]any](t, recursive.Document())[0])["name"] != "z" {
		t.Fatalf("typed source occurrences lost: %v", err)
	}
}

func TestTypedSensitiveProjectionRoundTripsOnlyWithPresence(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	fragment := func(value any) admission.Fragment {
		t.Helper()
		result, checkErr := admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		return result
	}
	input := fragment([]any{map[string]any{"platform_application_id": "app", "settings": []any{map[string]any{"setting_id": "token", "classification": "redacted", "value": ""}}}})
	safe, err := ProjectConcern("runtime-platform-applications", input, false, false)
	if err != nil {
		t.Fatal(err)
	}
	setting := requireType[map[string]any](t, requireType[[]any](t, requireType[map[string]any](t, requireType[[]any](t, safe.Document())[0])["settings"])[0])
	if setting["value"] != nil || setting["value_present"] != true {
		t.Fatalf("sensitive value was not projected: %#v", setting)
	}
	if _, err := ProjectConcern("runtime-platform-applications", safe, true, false); err != nil {
		t.Fatal(err)
	}
	if _, err := ProjectConcern("runtime-platform-applications", input, true, false); err == nil {
		t.Fatal("protected observation lacked its explicit presence marker")
	}
}

func TestSoftwareConcernCanProjectReferenceBeforeCollectionJoin(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	input, err := admission.AdmitFragment(owner, admission.RealizationValue, []any{map[string]any{"component_id": "component", "name": "library", "component_type": "library", "repository_refs": []any{"z", "a"}}}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	projected, err := ProjectConcern("runtime-software-components", input, false, true)
	if err != nil {
		t.Fatal(err)
	}
	refs := requireType[[]any](t, requireType[map[string]any](t, requireType[[]any](t, projected.Document())[0])["repository_refs"])
	if requireType[map[string]any](t, refs[0])["_identity"] != "z" {
		t.Fatal("recursive repository occurrences were reordered")
	}
	safe, err := sanitizeConcern("runtime-software-components", input.Document(), false, true)
	if err != nil {
		t.Fatal(err)
	}
	if requireType[[]any](t, requireType[map[string]any](t, requireType[[]any](t, safe)[0])["repository_refs"])[0] != "a" {
		t.Fatal("comparison-only repository identities entered the snapshot shape")
	}
}

func TestScalarComparisonUsesReferenceQuotedOrder(t *testing.T) {
	for input, want := range map[string]string{"a'b": `"a'b"`, "a\"b": `'a"b'`, "\x00\b\f\v\a": `'\x00\x08\x0c\x0b\x07'`} {
		if got := pythonStringRepr(input); got != want {
			t.Fatalf("quoted scalar = %q, want %q", got, want)
		}
	}
}
