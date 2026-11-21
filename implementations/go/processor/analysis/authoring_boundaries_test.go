package analysis

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func TestAuthoringReportLimitUsesNormalizedCarrier(t *testing.T) {
	row := authoringReportReference(t)
	report := testObject(t, row.Left.TransformationReport)
	object(report["preservation"])["limitations"] = []any{""}
	emptySize := len(testJSON(t, report))
	for _, size := range []int{65536, 65537} {
		object(report["preservation"])["limitations"] = []any{strings.Repeat("x", size-emptySize)}
		raw := testJSON(t, report)
		if len(raw) != size {
			t.Fatal("incorrect boundary probe")
		}
		checkAuthoringReportCarrier(t, row, raw, size == 65536, false)
	}
	padded := append(bytes.Clone(row.Left.TransformationReport), bytes.Repeat([]byte(" "), 65536)...)
	checkAuthoringReportCarrier(t, row, padded, true, true)
}

func authoringReportReference(t *testing.T) analysisReference {
	t.Helper()
	var fixture struct {
		Cases []analysisReference `json:"cases"`
	}
	raw := testGzip(t, readTestFile(t, "testdata/authoring-adapter-comparison.json.gz"))
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	for _, row := range fixture.Cases {
		if row.Expected["left_matches_expected"] == true && row.Left.OutputSource != nil && len(row.Left.TransformationReport) > 4 {
			return row
		}
	}
	t.Fatal("missing successful reference transformation")
	return analysisReference{}
}

func checkAuthoringReportCarrier(t *testing.T, row analysisReference, raw []byte, valid, matches bool) {
	t.Helper()
	request, err := row.request()
	if err != nil {
		t.Fatal(err)
	}
	request.Authoring.Left.TransformationReport, err = referenceAdmission("artifact-transformation-report-v1", raw, nil)
	if err != nil {
		t.Fatal(err)
	}
	got, err := AnalyzeContext(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	if (got.Document["left"] != nil) != valid || got.Document["left_matches_expected"] != matches {
		t.Fatalf("report bytes=%d valid=%v matches=%v: %v", len(raw), valid, matches, got.Document["reason_codes"])
	}
}

func TestAuthoringSemanticUncertaintyRemainsIncomparable(t *testing.T) {
	var fixture struct {
		Cases []struct {
			SourceTest       string          `json:"source_test"`
			SemanticResult   json.RawMessage `json:"semantic_result"`
			ExpectedRelation string          `json:"expected_relation"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(readTestFile(t, "testdata/semantic-uncertainty.json"), &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Cases) != 4 {
		t.Fatal("missing independent uncertainty probes")
	}
	for _, row := range fixture.Cases {
		t.Run(row.SourceTest, func(t *testing.T) {
			checkAuthoringUncertainty(t, row.SemanticResult, row.ExpectedRelation)
		})
	}
}

func TestAuthoringDiagnosticMultisetAndBounds(t *testing.T) {
	base := diagnostic.Diagnostic{Domain: "sdl", Code: "authoring.advisory", Severity: "warning", Address: "/nodes/web", Message: "bounded"}
	original, err := authoringDiagnosticDigest([]diagnostic.Diagnostic{base})
	if err != nil {
		t.Fatal(err)
	}
	changed := base
	changed.Message = "different prose"
	same, err := authoringDiagnosticDigest([]diagnostic.Diagnostic{changed})
	if err != nil || same != original {
		t.Fatal("human text changed semantic key")
	}
	checkAuthoringDiagnosticKeys(t, base, original)
	duplicate, err := authoringDiagnosticDigest([]diagnostic.Diagnostic{base, base})
	if err != nil || duplicate == original {
		t.Fatal("duplicate count lost")
	}
	for _, modify := range []func(*diagnostic.Diagnostic){func(d *diagnostic.Diagnostic) { d.Code = "" }, func(d *diagnostic.Diagnostic) { d.Severity = "fatal" }, func(d *diagnostic.Diagnostic) { d.Message = strings.Repeat("x", 513) }, func(d *diagnostic.Diagnostic) { d.Address = strings.Repeat("x", 4097) }, func(d *diagnostic.Diagnostic) { d.Message = string([]byte{255}) }} {
		changed := base
		modify(&changed)
		if _, invalidErr := authoringDiagnosticDigest([]diagnostic.Diagnostic{changed}); invalidErr == nil {
			t.Fatal("invalid diagnostic accepted")
		}
	}
	if _, err = authoringDiagnosticDigest(make([]diagnostic.Diagnostic, 65)); err == nil {
		t.Fatal("diagnostic count ignored")
	}
	source := base
	source.Domain = ""
	source.Stage = "sdl"
	source.Pointer = base.Address
	source.Address = ""
	same, err = authoringDiagnosticDigest([]diagnostic.Diagnostic{source})
	if err != nil || same != original {
		t.Fatal("source diagnostic projection drift")
	}
}

func TestAuthoringClassifiesOnlyUntrustedOutputFailures(t *testing.T) {
	for _, category := range []fault.Category{fault.InvalidInput, fault.EvidenceIntegrity, fault.Operational, fault.Authorization, fault.NotFound, fault.Conflict} {
		expected := category == fault.InvalidInput || category == fault.EvidenceIntegrity
		if authoringInvalidOutput(fault.New(category, "bounded", nil)) != expected {
			t.Fatal("wrong observation failure classification", category)
		}
	}
	if authoringInvalidOutput(errors.New("unexpected implementation failure")) {
		t.Fatal("implementation failure was hidden")
	}
}

func TestAuthoringVectorPinsAndPortableRenameIdentifiers(t *testing.T) {
	owner, err := analysisOwner()
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 128 << 10, MaxDepth: 64}
	for _, name := range []string{"front", "front-door", "front_1", "Front", "_front", strings.Repeat("x", 65), "front\n"} {
		operation := map[string]any{"profile": "rename-sdl-declaration/v1", "target_address": "nodes.web", "new_local_name": name}
		err = owner.CheckModelFragment("authoring-adapter-vector-v1", "#/$defs/AuthoringOperationModel", testJSON(t, operation), limits)
		valid := name == "front" || name == "front-door" || name == "front_1"
		if (err == nil) != valid {
			t.Fatalf("rename identifier %q: %v", name, err)
		}
	}
	raw := readTestFile(t, "../../../../contracts/fixtures/authoring-adapters-v1/cases/strict-source.json")
	for _, change := range []func(map[string]any){
		func(v map[string]any) { v["input_digest"] = "sha256:" + strings.Repeat("0", 64) },
		func(v map[string]any) { v["operation_digest"] = "sha256:" + strings.Repeat("0", 64) },
		func(v map[string]any) { object(v["operation"])["profile"] = "unknown/v1" },
		func(v map[string]any) { object(v["operation"])["target_address"] = "nodes.web" },
		func(v map[string]any) { v["unknown"] = true },
	} {
		value := testObject(t, raw)
		change(value)
		if _, err = owner.Validate("authoring-adapter-vector-v1", testJSON(t, value), limits, nil); err == nil {
			t.Fatal("unbound authoring vector admitted")
		}
	}
}

func checkAuthoringDiagnosticKeys(t *testing.T, base diagnostic.Diagnostic, original string) {
	t.Helper()
	for _, modify := range []func(*diagnostic.Diagnostic){func(d *diagnostic.Diagnostic) { d.Domain = "other" }, func(d *diagnostic.Diagnostic) { d.Code = "other" }, func(d *diagnostic.Diagnostic) { d.Severity = "info" }, func(d *diagnostic.Diagnostic) { d.Address = "/nodes/other" }} {
		changed := base
		modify(&changed)
		actual, err := authoringDiagnosticDigest([]diagnostic.Diagnostic{changed})
		if err != nil || actual == original {
			t.Fatal("diagnostic key omitted coordinate")
		}
		a, err := authoringDiagnosticDigest([]diagnostic.Diagnostic{changed, base})
		if err != nil {
			t.Fatal(err)
		}
		b, err := authoringDiagnosticDigest([]diagnostic.Diagnostic{base, changed})
		if err != nil || a != b {
			t.Fatal("diagnostic order changed multiset")
		}
	}
}

func checkAuthoringUncertainty(t *testing.T, raw []byte, expected string) {
	t.Helper()
	value, admissionErr := referenceAdmission("semantic-comparison-result-v1", raw, nil)
	// The incumbent context monkeypatch replaces its reason without
	// updating the governed impact scope. Native opaque Values refuse
	// that inconsistent carrier before semantic interpretation.
	if strings.Contains(string(raw), "impact-scope-partial") {
		if category, ok := fault.CategoryOf(admissionErr); !ok || category != fault.InvalidInput {
			t.Fatalf("inconsistent injected carrier admitted: %v", admissionErr)
		}
		return
	}
	if admissionErr != nil {
		t.Fatal(admissionErr)
	}
	relation, err := authoringSemanticRelation(value)
	if err != nil || relation != expected {
		t.Fatalf("uncertain semantic result promoted: %s, %v", relation, err)
	}
}
