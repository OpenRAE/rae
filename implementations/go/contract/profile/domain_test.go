package profile

import (
	"bytes"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type domainVectors struct {
	Resolutions []struct {
		Name       string          `json:"name"`
		Raw        json.RawMessage `json:"coordinate"`
		Context    json.RawMessage `json:"context"`
		Resolution struct {
			Outcome     string             `json:"outcome"`
			Definition  json.RawMessage    `json:"definition"`
			Provenance  *provenanceVector  `json:"provenance"`
			Diagnostics []diagnosticVector `json:"diagnostics"`
		} `json:"resolution"`
	} `json:"resolutions"`
	Admissions []struct {
		Name     string            `json:"name"`
		Bindings []json.RawMessage `json:"bindings"`
		Context  json.RawMessage   `json:"context"`
		Policy   json.RawMessage   `json:"policy"`
		Report   reportVector      `json:"report"`
	} `json:"admissions"`
}

type reportVector struct {
	Results []struct {
		BindingID          string             `json:"binding_id"`
		Outcome            string             `json:"outcome"`
		ResolutionOutcome  string             `json:"resolution_outcome"`
		StructurallyValid  bool               `json:"structurally_valid"`
		SemanticsSupported bool               `json:"semantics_supported"`
		Opaque             bool               `json:"opaque"`
		Provenance         *provenanceVector  `json:"provenance"`
		Basis              string             `json:"basis"`
		Diagnostics        []diagnosticVector `json:"diagnostics"`
	} `json:"results"`
	BindingsTotal        int  `json:"bindings_total"`
	DiagnosticsTruncated bool `json:"diagnostics_truncated"`
	Admitted             bool `json:"admitted"`
}

type provenanceVector struct {
	SourceLocator   string `json:"source_locator"`
	SourceDigest    string `json:"source_digest"`
	TrustDecisionID string `json:"trust_decision_id"`
}

type diagnosticVector struct {
	Code     string `json:"code"`
	Domain   string `json:"domain"`
	Address  string `json:"address"`
	Message  string `json:"message"`
	Severity string `json:"severity"`
}

func readDomainVectors(t *testing.T) domainVectors {
	t.Helper()
	data, err := os.ReadFile("testdata/domain-vectors.json")
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	var vectors domainVectors
	if err := json.Unmarshal(data, &vectors); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	return vectors
}

func diagnostics(vectors []diagnosticVector) []diagnostic.Diagnostic {
	var result []diagnostic.Diagnostic
	for _, v := range vectors {
		result = append(result, diagnostic.Diagnostic{Code: v.Code, Domain: v.Domain, Address: v.Address, Message: v.Message, Severity: v.Severity})
	}
	return result
}

func provenance(v *provenanceVector) *DomainProvenance {
	if v == nil {
		return nil
	}
	return &DomainProvenance{SourceLocator: v.SourceLocator, SourceDigest: v.SourceDigest, TrustDecisionID: v.TrustDecisionID}
}

func decodeJSON(t *testing.T, data []byte, target any) {
	t.Helper()
	if err := json.Unmarshal(data, target); err != nil {
		t.Fatalf("json.Unmarshal(%T) error = %v", target, err)
	}
}

func jsonValue(t *testing.T, data []byte) any {
	t.Helper()
	var value any
	decodeJSON(t, data, &value)
	return value
}

func bindingOf(t *testing.T, data []byte) binding.DomainProfileBindingV1 {
	t.Helper()
	var value binding.DomainProfileBindingV1
	decodeJSON(t, data, &value)
	return value
}

func policyOf(t *testing.T, data []byte) binding.DomainProfileAdmissionPolicyV1 {
	t.Helper()
	var value binding.DomainProfileAdmissionPolicyV1
	decodeJSON(t, data, &value)
	return value
}

func checkDefinition(t *testing.T, want json.RawMessage, got *binding.DomainProfileDefinitionV1) {
	t.Helper()
	if string(want) == "null" || want == nil {
		if got != nil {
			t.Errorf("Definition = %+v, want nil", got)
		}
		return
	}
	encoded, err := json.Marshal(got)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	if diff := cmp.Diff(jsonValue(t, want), jsonValue(t, encoded)); diff != "" {
		t.Errorf("Definition mismatch (-want +got):\n%s", diff)
	}
}

func TestDomainResolutionMatchesTheReference(t *testing.T) {
	for _, v := range readDomainVectors(t).Resolutions {
		t.Run(v.Name, func(t *testing.T) {
			var raw map[string]string
			decodeJSON(t, v.Raw, &raw)
			coordinate := DomainCoordinate{Namespace: raw["namespace"], Authority: raw["authority"], ProfileID: raw["profile_id"], Revision: raw["revision"], DefinitionDigest: raw["definition_digest"]}
			got, err := mustLoad(t).ResolveDomainProfile(coordinate, v.Context)
			if err != nil {
				t.Fatalf("ResolveDomainProfile() error = %v", err)
			}
			want := DomainResolution{Outcome: DomainResolutionOutcome(v.Resolution.Outcome), Provenance: provenance(v.Resolution.Provenance), Diagnostics: diagnostics(v.Resolution.Diagnostics)}
			gotDefinition := got.Definition
			got.Definition = nil
			if diff := cmp.Diff(want, got); diff != "" {
				t.Errorf("ResolveDomainProfile() mismatch (-want +got):\n%s", diff)
			}
			checkDefinition(t, v.Resolution.Definition, gotDefinition)
		})
	}
}

func TestDomainAdmissionMatchesTheReference(t *testing.T) {
	for _, v := range readDomainVectors(t).Admissions {
		t.Run(v.Name, func(t *testing.T) {
			bindings := make([]binding.DomainProfileBindingV1, 0, len(v.Bindings))
			for _, raw := range v.Bindings {
				bindings = append(bindings, bindingOf(t, raw))
			}
			got, err := mustLoad(t).AdmitDomainBindings(bindings, v.Context, policyOf(t, v.Policy))
			if err != nil {
				t.Fatalf("AdmitDomainBindings() error = %v", err)
			}
			if diff := cmp.Diff(expectedReport(v.Report), got); diff != "" {
				t.Errorf("AdmitDomainBindings() mismatch (-want +got):\n%s", diff)
			}
			if got.Admitted() != v.Report.Admitted {
				t.Errorf("Admitted() = %t, want %t", got.Admitted(), v.Report.Admitted)
			}
		})
	}
}

func expectedReport(report reportVector) DomainAdmissionReport {
	want := DomainAdmissionReport{BindingsTotal: report.BindingsTotal, DiagnosticsTruncated: report.DiagnosticsTruncated}
	for _, r := range report.Results {
		want.Results = append(want.Results, DomainBindingAdmission{BindingID: r.BindingID, Outcome: DomainAdmissionOutcome(r.Outcome), ResolutionOutcome: DomainResolutionOutcome(r.ResolutionOutcome), StructurallyValid: r.StructurallyValid, SemanticsSupported: r.SemanticsSupported, Opaque: r.Opaque, Provenance: provenance(r.Provenance), Basis: r.Basis, Diagnostics: diagnostics(r.Diagnostics)})
	}
	return want
}

func TestDomainOperationsRefuseInvalidInputs(t *testing.T) {
	vectors := readDomainVectors(t)
	valid := vectors.Admissions[0]
	context := []byte(valid.Context)
	policy := policyOf(t, valid.Policy)
	good := bindingOf(t, valid.Bindings[0])
	for name, call := range map[string]func() error{
		"unsorted policy operations": func() error {
			_, err := mustLoad(t).AdmitDomainBindings([]binding.DomainProfileBindingV1{good}, context, policyOf(t, []byte(`{"schema_version":"domain-profile-admission-policy/v1","required_operations":["typed-report","execution"]}`)))
			return err
		},
		"empty context": func() error {
			_, err := mustLoad(t).AdmitDomainBindings(nil, []byte(`{}`), policy)
			return err
		},
		"empty binding": func() error {
			_, err := mustLoad(t).AdmitDomainBindings([]binding.DomainProfileBindingV1{{}}, context, policy)
			return err
		},
		"empty resolution context": func() error {
			_, err := mustLoad(t).ResolveDomainProfile(DomainCoordinate{}, []byte(`{"schema_version":"domain-profile-resolution-context/v1","namespace_admissions":[],"definitions":[1]}`))
			return err
		},
	} {
		if category, code := faultCode(call()); category != fault.InvalidInput || code != "domain-profile-input-invalid" {
			t.Errorf("%s: error code = %s, want InvalidInput domain-profile-input-invalid", name, code)
		}
	}
}

func TestDomainLimitsBounds(t *testing.T) {
	if err := DefaultDomainLimits().Validate(); err != nil {
		t.Fatalf("DefaultDomainLimits().Validate() error = %v", err)
	}
	upper := DomainLimits{4096, 4096, 64, 65536, 16777216, 4096, 1048576, 256}
	lower := DomainLimits{1, 1, 1, 1, 1, 0, 1, 1}
	for name, limits := range map[string]DomainLimits{"upper": upper, "lower": lower} {
		if err := limits.Validate(); err != nil {
			t.Errorf("%s bounds Validate() error = %v, want nil", name, err)
		}
	}
	fields := func(l *DomainLimits) []*int {
		return []*int{&l.MaxDefinitions, &l.MaxBindings, &l.MaxDepth, &l.MaxNodes, &l.MaxScalarBytes, &l.MaxReferences, &l.MaxEvaluations, &l.MaxDiagnostics}
	}
	for i := range fields(&upper) {
		over, under := upper, lower
		*fields(&over)[i]++
		*fields(&under)[i]--
		for name, limits := range map[string]DomainLimits{"over": over, "under": under} {
			if category, code := faultCode(limits.Validate()); category != fault.InvalidInput || code != "domain-profile-limits-invalid" {
				t.Errorf("field %d %s: Validate() = %s, want InvalidInput domain-profile-limits-invalid", i, name, code)
			}
		}
	}
}

func TestParseDomainBindingIsBoundedAndStrict(t *testing.T) {
	vectors := readDomainVectors(t)
	var compact bytes.Buffer
	if err := json.Compact(&compact, vectors.Admissions[0].Bindings[0]); err != nil {
		t.Fatalf("json.Compact() error = %v", err)
	}
	raw := compact.Bytes()
	parsed, err := mustLoad(t).ParseDomainBinding(raw, 1<<20, DefaultDomainLimits())
	if err != nil {
		t.Fatalf("ParseDomainBinding(reference) error = %v", err)
	}
	encoded, err := json.Marshal(parsed)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	if diff := cmp.Diff(jsonValue(t, raw), jsonValue(t, encoded)); diff != "" {
		t.Errorf("ParseDomainBinding() round trip mismatch (-want +got):\n%s", diff)
	}
	text := string(raw)
	duplicate := replaceFirst(text, `"value":{"name":"private-mirror"}`, `"value":{"name":"one","name":"two"}`)
	if duplicate == text {
		t.Fatalf("reference binding has no replaceable value: %s", text[:120])
	}
	small := DefaultDomainLimits()
	small.MaxNodes = 3
	for name, tc := range map[string]struct {
		data     string
		maxBytes int
		limits   DomainLimits
		code     string
	}{
		"duplicate member": {duplicate, 1 << 20, DefaultDomainLimits(), "domain-profile-input-invalid"},
		"byte limit":       {text, len(text) - 1, DefaultDomainLimits(), "domain-profile-input-invalid"},
		"node limit":       {text, 1 << 20, small, "domain-profile-input-invalid"},
		"array root":       {"[" + text + "]", 1 << 20, DefaultDomainLimits(), "domain-profile-input-invalid"},
		"model rule":       {replaceFirst(text, `"evidence_refs":[]`, `"evidence_refs":["x"]`), 1 << 20, DefaultDomainLimits(), "domain-profile-input-invalid"},
		"schema":           {replaceFirst(text, `"use":"constraint"`, `"use":"unknown-use"`), 1 << 20, DefaultDomainLimits(), "domain-profile-input-invalid"},
		"invalid limits":   {text, 1 << 20, DomainLimits{}, "domain-profile-limits-invalid"},
		"invalid maxBytes": {text, 0, DefaultDomainLimits(), "domain-profile-limits-invalid"},
	} {
		_, err := mustLoad(t).ParseDomainBinding([]byte(tc.data), tc.maxBytes, tc.limits)
		if category, code := faultCode(err); category != fault.InvalidInput || code != tc.code {
			t.Errorf("%s: ParseDomainBinding() = %s (%v), want InvalidInput %s", name, code, err, tc.code)
		}
	}
}

func replaceFirst(text, old, replacement string) string {
	return strings.Replace(text, old, replacement, 1)
}

func TestDomainDefinitionDigestMatchesTheReference(t *testing.T) {
	checked := 0
	for _, v := range readDomainVectors(t).Resolutions {
		var context struct {
			Definitions []struct {
				Definition json.RawMessage `json:"definition"`
			} `json:"definitions"`
		}
		if err := json.Unmarshal(v.Context, &context); err != nil {
			t.Fatalf("json.Unmarshal() error = %v", err)
		}
		for _, item := range context.Definitions {
			var definition binding.DomainProfileDefinitionV1
			decodeJSON(t, item.Definition, &definition)
			var fields struct {
				Coordinate struct {
					DefinitionDigest string `json:"definition_digest"`
				} `json:"coordinate"`
			}
			decodeJSON(t, item.Definition, &fields)
			want := fields.Coordinate.DefinitionDigest
			got, err := DomainDefinitionDigest(definition)
			if err != nil || got != want {
				t.Errorf("%s: DomainDefinitionDigest() = %s, %v; want %v", v.Name, got, err, want)
			}
			checked++
		}
	}
	if checked == 0 {
		t.Fatal("no reference definitions were checked")
	}
}
