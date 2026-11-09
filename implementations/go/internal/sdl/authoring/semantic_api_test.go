package authoring

import (
	"bytes"
	"errors"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type semanticVector struct {
	RecordExplicitness bool                          `json:"record_explicitness"`
	Explicitness       map[string]ExplicitnessRecord `json:"explicitness"`
	AdmissionError     string                        `json:"admission_error"`
	Name               string                        `json:"name"`
	Source             string                        `json:"source"`
	Canonical          string                        `json:"canonical"`
	CanonicalError     string                        `json:"canonical_error"`
	Digest             string                        `json:"digest"`
	Accepted           bool                          `json:"accepted"`
	Findings           []semanticFindingVector       `json:"findings"`
	Advisories         []string                      `json:"advisories"`
	Locations          []*semanticLocationVector     `json:"locations"`
}
type semanticFindingVector struct {
	Message string   `json:"message"`
	Owner   []string `json:"owner"`
	Pointer *string  `json:"pointer"`
}
type semanticLocationVector struct {
	Path         string       `json:"path"`
	OriginalPath string       `json:"original_path"`
	Source       string       `json:"source"`
	Range        source.Range `json:"range"`
}

func TestSemanticReference(t *testing.T) {
	cases := readSemanticVectors(t)
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) { checkSemanticVector(t, parser, c) })
	}
}
func checkSemanticVector(t *testing.T, parser *Parser, vector semanticVector) {
	t.Helper()
	document, err := parser.Decode(Request{Source: []byte(vector.Source), Name: "main.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	checkConstructedSemanticVector(t, parser, document, vector)
}
func checkConstructedSemanticVector(t *testing.T, parser *Parser, document *Document, vector semanticVector) {
	t.Helper()
	admitted, advisories, err := parser.Validate(document)
	if vector.AdmissionError != "" {
		var coded interface{ Code() string }
		if admitted != nil || len(advisories) != 0 || !errors.As(err, &coded) || coded.Code() != "sdl-materialized-portable-bounds" {
			t.Fatalf("portable admission = %v, %v, %v; want bounded refusal", admitted, advisories, err)
		}
		return
	}
	if vector.RecordExplicitness {
		checkSemanticExplicitness(t, parser, document, admitted, vector)
	}
	if (err == nil) != vector.Accepted {
		t.Fatalf("admission = %v; want accepted %v", err, vector.Accepted)
	}
	checkSemanticAdvisories(t, advisories, vector.Advisories)
	if vector.Accepted {
		checkSemanticIdentity(t, admitted, vector)
		return
	}
	var refusal diagnostic.Error
	if admitted != nil || !errors.As(err, &refusal) {
		t.Fatalf("refusal = %v; want diagnostic error without admitted document", err)
	}
	checkSemanticFindings(t, refusal.Diagnostics(), vector)
	if document.contract == materializedContract {
		formatErr := parser.checkMaterializedFormat(document)
		if !errors.As(formatErr, &refusal) {
			t.Fatalf("materialized format refusal = %v; want semantic findings", formatErr)
		}
		checkSemanticFindings(t, refusal.Diagnostics(), vector)
	}
}

func checkSemanticExplicitness(t *testing.T, parser *Parser, document, admitted *Document, vector semanticVector) {
	t.Helper()
	var records map[string]ExplicitnessRecord
	if admitted != nil {
		records = admitted.Explicitness()
	} else {
		if document.expanded != nil {
			document = document.expanded
		}
		model, err := parser.newSemanticModel(document)
		if err != nil {
			t.Fatal(err)
		}
		if err = model.loadIntent(); err != nil {
			t.Fatal(err)
		}
		records = model.intent.records
	}
	if len(records) != len(vector.Explicitness) {
		t.Errorf("explicitness record count = %d; want %d", len(records), len(vector.Explicitness))
	}
	for path, want := range vector.Explicitness {
		actual := records[path]
		if actual.Path != want.Path || actual.Classification != want.Classification || actual.Provenance != want.Provenance || actual.Reason != want.Reason || !slices.Equal(actual.Variables, want.Variables) || (actual.Variables == nil) != (want.Variables == nil) {
			t.Fatalf("explicitness at %q = %+v; want %+v", path, records[path], want)
		}
	}
}
func checkSemanticAdvisories(t *testing.T, actual []diagnostic.Diagnostic, expected []string) {
	t.Helper()
	if len(actual) != len(expected) {
		t.Fatalf("advisories = %v; want %v", actual, expected)
	}
	for i, warning := range actual {
		if warning.Message != expected[i] || warning.Severity != "warning" {
			t.Errorf("advisory = %v; want %s", warning, expected[i])
		}
	}
}
func checkSemanticIdentity(t *testing.T, admitted *Document, vector semanticVector) {
	t.Helper()
	canonical, err := admitted.CanonicalBytes()
	if vector.CanonicalError != "" {
		if err == nil {
			t.Fatal("canonicalization accepted an unsupported domain")
		}
		if _, err = admitted.CanonicalDigest(); err == nil {
			t.Fatal("digest accepted an unsupported canonical domain")
		}
		return
	}
	if err != nil || string(canonical) != vector.Canonical {
		t.Errorf("canonical = %s, %v; want %s", canonical, err, vector.Canonical)
	}
	digest, err := admitted.CanonicalDigest()
	if err != nil || digest != vector.Digest {
		t.Errorf("digest = %s, %v; want %s", digest, err, vector.Digest)
	}
}
func checkSemanticFindings(t *testing.T, findings []diagnostic.Diagnostic, vector semanticVector) {
	t.Helper()
	if len(findings) != len(vector.Findings) {
		t.Fatalf("findings = %v; want %v", findings, vector.Findings)
	}
	for i, finding := range findings {
		if finding.Message != vector.Findings[i].Message {
			t.Errorf("finding %d = %s; want %s", i, finding.Message, vector.Findings[i].Message)
		}
		checkSemanticLocation(t, finding, vector.Locations[i])
	}
}
func checkSemanticLocation(t *testing.T, actual diagnostic.Diagnostic, expected *semanticLocationVector) {
	t.Helper()
	if expected == nil {
		if actual.Range != nil || actual.Source != "" || actual.OriginalPointer != "" {
			t.Errorf("unowned finding has invented source location: %+v", actual)
		}
		return
	}
	want := diagnostic.Range{StartLine: expected.Range.Start.Line, StartColumn: expected.Range.Start.Column, EndLine: expected.Range.End.Line, EndColumn: expected.Range.End.Column}
	if actual.Pointer != expected.Path || actual.OriginalPointer != expected.OriginalPath || actual.Source != expected.Source || actual.Range == nil || *actual.Range != want {
		t.Errorf("location = %+v; want %s %s %v", actual, expected.Source, expected.Path, want)
	}
}

func TestSemanticAdmissionRequiresConstructedDocument(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, document := range []*Document{nil, {}} {
		if document.Validated() {
			t.Fatal("zero document claims semantic admission")
		}
		if _, err = document.CanonicalBytes(); err == nil {
			t.Fatal("zero document produced canonical bytes")
		}
		if admitted, _, err := parser.Validate(document); err == nil || admitted != nil {
			t.Fatal("zero document passed semantic admission")
		}
	}
}

func TestSemanticAdmissionSealsFreshDocument(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	document, err := parser.Decode(Request{Source: []byte("name: example\n")})
	if err != nil {
		t.Fatal(err)
	}
	if document.Validated() {
		t.Fatal("construction granted semantic admission")
	}
	if _, err = document.CanonicalDigest(); err == nil {
		t.Fatal("construction granted semantic identity")
	}
	admitted, advisories, err := parser.Validate(document)
	if err != nil {
		t.Fatal(err)
	}
	if admitted == document || !admitted.Validated() || document.Validated() || len(advisories) != 0 {
		t.Fatal("admission did not preserve the constructed input and seal a separate result")
	}
	want := []byte(`{"module_node_variable_refs":{},"module_variable_specs":{},"profile":"raes-sdl-semantic/v2","scenario":{"name":"example"}}`)
	got, err := admitted.CanonicalBytes()
	if err != nil || !bytes.Equal(got, want) {
		t.Fatalf("canonical bytes = %s, %v; want %s", got, err, want)
	}
	clear(got)
	clear(admitted.JSON())
	got, err = admitted.CanonicalBytes()
	if err != nil || !bytes.Equal(got, want) {
		t.Fatal("caller mutation changed admitted identity")
	}
}

func TestSemanticAdmissionCollectsFailuresAndKeepsAdvisories(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	document, err := parser.Decode(Request{Source: []byte("name: example\nnodes:\n  web:\n    type: compute\n    features: {missing: absent}\nfeatures:\n  install: {type: service, dependencies: [other]}\n"), Name: "main.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	admitted, advisories, err := parser.Validate(document)
	var failure diagnostic.Error
	if admitted != nil || !errors.As(err, &failure) || failure.Category() != fault.InvalidInput {
		t.Fatalf("semantic refusal = %v, %v; want classified failure without admitted document", admitted, err)
	}
	findings := failure.Diagnostics()
	want := []string{
		"Node 'web' references undefined feature 'missing'",
		"Node 'web' feature 'missing' references undefined role 'absent'",
		"Feature 'install' depends on undefined feature 'other'",
	}
	if len(findings) != len(want) {
		t.Fatalf("findings = %v; want %v", findings, want)
	}
	for i, finding := range findings {
		if finding.Message != want[i] || finding.Code != "sdl.semantic" || finding.Severity != "error" || finding.Stage != "semantic_validation" || finding.Source != "main.yaml" || finding.Range == nil {
			t.Errorf("finding %d = %+v; want located semantic error %q", i, finding, want[i])
		}
	}
	if len(advisories) != 1 || advisories[0].Severity != "warning" {
		t.Fatalf("advisories = %v; want missing-resource warning alongside refusal", advisories)
	}
	findings[0].Message = "changed"
	findings[0].Range.StartLine = 999
	if copied := failure.Diagnostics(); copied[0].Message != want[0] || copied[0].Range.StartLine == 999 {
		t.Fatal("caller changed retained findings")
	}
}

func TestMaterializedInfrastructureCycleMatchesReference(t *testing.T) {
	// The reference checks workflow and feature cycles. Infrastructure cycles
	// have no additional rejection at this boundary.
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	document, err := parser.Decode(Request{Source: []byte("name: example\nnodes: {a: {type: compute}, b: {type: compute}}\ninfrastructure: {a: {dependencies: [b]}, b: {dependencies: [a]}}\n")})
	if err != nil {
		t.Fatal(err)
	}

	if err := parser.checkMaterializedFormat(document); err != nil {
		t.Fatalf("infrastructure cycle = %v; want reference acceptance", err)
	}
}
