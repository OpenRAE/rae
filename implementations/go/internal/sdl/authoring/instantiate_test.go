package authoring

import (
	"bytes"
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type instantiationReference struct {
	Name           string            `json:"name"`
	Operation      string            `json:"operation"`
	Source         string            `json:"source"`
	Files          map[string]string `json:"files"`
	Profile        string            `json:"profile"`
	Parameters     map[string]any    `json:"parameters"`
	Outcomes       json.RawMessage   `json:"outcomes"`
	Payload        json.RawMessage   `json:"payload"`
	Output         json.RawMessage   `json:"output"`
	SnapshotDigest string            `json:"snapshot_digest"`
	Accepted       bool              `json:"accepted"`
	Findings       []string          `json:"findings"`
	CheckFindings  bool              `json:"check_findings"`
}

func TestInstantiationReference(t *testing.T) {
	parser := operationParser(t)
	raw, err := readCompressedFixture("testdata/instantiation.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []instantiationReference `json:"cases"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err = decoder.Decode(&fixture); err != nil {
		t.Fatal(err)
	}
	for _, vector := range fixture.Cases {
		t.Run(vector.Name, func(t *testing.T) {
			vector.check(t, parser)
		})
	}
}

func (v instantiationReference) check(t *testing.T, parser *Parser) {
	t.Helper()
	result, err := v.run(t, parser)
	if (err == nil) != v.Accepted {
		t.Fatalf("admission = %#v; want accepted %v", err, v.Accepted)
	}
	if !v.Accepted {
		if v.CheckFindings {
			assertInstantiationFindings(t, err, v.Findings)
		}
		return
	}
	assertJSONReference(t, "output", result.JSON(), v.Output)
	snapshot, err := result.Snapshot()
	if err != nil {
		t.Fatal(err)
	}
	if got := digest.SHA256(snapshot); got != v.SnapshotDigest {
		t.Errorf("snapshot digest=%s; want %s", got, v.SnapshotDigest)
	}
}

func operationParser(t *testing.T) *Parser {
	t.Helper()
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	return parser
}

func operationDocument(t *testing.T, parser *Parser, text string) *Document {
	t.Helper()
	document, err := parser.Decode(Request{Source: []byte(text), Name: "main.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	return document
}

func TestInstantiationBindsTypedValuesAndOwnsResult(t *testing.T) {
	parser := operationParser(t)
	owner := parser
	document := operationDocument(t, parser, "name: family\ndescription: 'enabled-${enabled}'\nvariables:\n  enabled: {type: boolean, default: false}\n")
	before := document.JSON()
	instantiated, err := owner.Instantiate(document, nil, "")
	if err != nil || instantiated == nil || !instantiated.Validated() {
		t.Fatalf("instantiation = %v, %v; want admitted concrete document", instantiated, err)
	}
	var payload map[string]json.RawMessage
	if err = json.Unmarshal(instantiated.JSON(), &payload); err != nil {
		t.Fatal(err)
	}
	if string(payload["description"]) != `"enabled-False"` || payload["variables"] != nil || payload["instantiation_provenance"] == nil {
		t.Fatalf("concrete payload = %s; want Python scalar rendering, provenance, and no variables", instantiated.JSON())
	}
	if !bytes.Equal(before, document.JSON()) || document.Validated() {
		t.Fatal("instantiation changed the input document")
	}
	if _, err = owner.AdmitInstantiated(instantiated.JSON()); err != nil {
		t.Fatalf("independent admission = %v; want success", err)
	}
}

func TestInstantiationCollectsBindingErrorsAndRedactsValues(t *testing.T) {
	parser := operationParser(t)
	owner := parser
	document := operationDocument(t, parser, "name: family\nvariables:\n  first: {type: integer, required: true}\n  second: {type: string, allowed_values: [safe]}\n")
	result, err := owner.Instantiate(document, map[string]any{"second": "private-value", "extra": true}, "")
	var refusal diagnostic.Error
	if result != nil || !errors.As(err, &refusal) || len(refusal.Diagnostics()) != 3 {
		t.Fatalf("binding refusal = %v, %v; want three ordered findings without a document", result, err)
	}
	for index, name := range []string{"first", "second", "extra"} {
		finding := refusal.Diagnostics()[index]
		if finding.Stage != "instantiation" || !strings.Contains(finding.Message, name) || strings.Contains(finding.Message, "private-value") {
			t.Errorf("finding %d = %+v; want ordered value-free instantiation error", index, finding)
		}
	}
}

func TestInstantiationRejectsIntroducedTokensAndForgedFlags(t *testing.T) {
	parser := operationParser(t)
	owner := parser
	document := operationDocument(t, parser, "name: family\ndescription: '${message}'\nvariables:\n  message: {type: string, default: safe}\n")
	if result, err := owner.Instantiate(document, map[string]any{"message": "${message}"}, ""); result != nil || err == nil {
		t.Fatal("a substituted token was admitted as concrete content")
	}
	valid, err := owner.Instantiate(document, nil, "")
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err = json.Unmarshal(valid.JSON(), &payload); err != nil {
		t.Fatal(err)
	}
	payload["_semantic_validated"] = true
	payload["description"] = "${message}"
	forged, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	if result, err := owner.AdmitInstantiated(forged); result != nil || err == nil {
		t.Fatal("caller-supplied validation state bypassed native phase admission")
	}
}

func (v instantiationReference) run(t *testing.T, parser *Parser) (*Document, error) {
	t.Helper()
	if v.Operation == "admit" {
		return parser.AdmitInstantiated(v.Payload)
	}
	files := fstest.MapFS{}
	for name, raw := range v.Files {
		files[name] = &fstest.MapFile{Data: []byte(raw)}
	}
	input, err := parser.Decode(Request{Source: []byte(v.Source), Name: "main.yaml", FS: files})
	if err != nil {
		t.Fatal(err)
	}
	if v.Operation != "select" {
		return parser.Instantiate(input, v.Parameters, v.Profile)
	}
	family, err := parser.AdmitFamily(input)
	if err != nil {
		return nil, err
	}
	return parser.Select(family, v.Outcomes, nil)
}

func assertInstantiationFindings(t *testing.T, err error, want []string) {
	t.Helper()
	carrier, ok := errors.AsType[diagnostic.Error](err)
	if !ok {
		t.Fatalf("expected structured instantiation diagnostics: %v", err)
	}
	got := []string{}
	for _, finding := range carrier.Diagnostics() {
		got = append(got, finding.Message)
	}
	if !slices.Equal(got, want) {
		t.Fatalf("findings=%q; want %q", got, want)
	}
}
