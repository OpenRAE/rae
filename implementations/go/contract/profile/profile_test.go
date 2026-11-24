package profile

import (
	"errors"
	"io/fs"
	"maps"
	"strings"
	"sync"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// testSchemas compiles the published schemas once for the package tests.
var testSchemas = sync.OnceValues(func() (*validation.Validator, error) { return validation.New(nil) }) //nolint:gochecknoglobals // Read-only compiled schemas shared by the package tests.

func schemas(t *testing.T) *validation.Validator {
	t.Helper()
	v, err := testSchemas()
	if err != nil {
		t.Fatalf("validation.New() error = %v", err)
	}
	return v
}

func mustLoad(t *testing.T) *Profiles {
	t.Helper()
	p, err := Load(schemas(t))
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	return p
}

func mustAuthority(t *testing.T) *concept.Authority {
	t.Helper()
	a, err := concept.Load(schemas(t))
	if err != nil {
		t.Fatalf("concept.Load() error = %v", err)
	}
	return a
}

func faultCode(err error) (fault.Category, string) {
	if refused, ok := errors.AsType[*fault.Error](err); ok {
		return refused.Category(), refused.Code()
	}
	return 0, ""
}

func TestLoadReadsEveryPackagedProfile(t *testing.T) {
	p := mustLoad(t)
	documents := p.Documents()
	if len(documents) != 26 {
		t.Fatalf("len(Documents()) = %d, want the 26 schema-bound profiles", len(documents))
	}
	for i, document := range documents {
		if document.ContractID == "" || len(document.JSON) == 0 || i > 0 && documents[i-1].Path >= document.Path {
			t.Errorf("Documents()[%d] = %q (%s), want a contract, content and path order", i, document.Path, document.ContractID)
		}
	}
	documents[0].JSON[0] = 'x'
	if p.Documents()[0].JSON[0] != '{' {
		t.Errorf("Documents() shares state with an earlier result")
	}
	if _, err := Load(nil); err == nil {
		t.Errorf("Load(nil) error = nil, want refusal")
	}
}

func packagedCopy(t *testing.T) fstest.MapFS {
	t.Helper()
	source, err := corpus.Open()
	if err != nil {
		t.Fatalf("corpus.Open() error = %v", err)
	}
	files := fstest.MapFS{}
	for _, file := range packagedFiles() {
		data, err := fs.ReadFile(source, file.Path)
		if err != nil {
			t.Fatalf("ReadFile(%q) error = %v", file.Path, err)
		}
		files[file.Path] = &fstest.MapFile{Data: data}
	}
	return files
}

func TestLoadRefusesDamagedProfiles(t *testing.T) {
	files := packagedCopy(t)
	if _, err := load(files, schemas(t)); err != nil {
		t.Fatalf("load(packaged copy) error = %v", err)
	}
	v1 := string(files[comparisonDir+"reference-v1.json"].Data)
	cases := map[string]struct{ path, data string }{
		"missing profile":           {path: pathValidation},
		"schema failure":            {path: pathValidation, data: `{"schema_version":"validation-profile-catalog/v1"}`},
		"history revision mismatch": {path: relationHistory()[0].path, data: string(files[relationDir+"participant-opacity-baseline-v1.json"].Data)},
		"profile above 256 KiB":     {path: relationDir + "participant-opacity-theorem-v1.json", data: string(files[relationDir+"participant-opacity-theorem-v1.json"].Data) + strings.Repeat(" ", MaxRelationProfileBytes)},
		"profile identity mismatch": {path: relationDir + "participant-opacity-theorem-v1.json", data: string(files[relationDir+"participant-opacity-baseline-v1.json"].Data)},
		"assessment revision":       {path: completenessDir + "delivery-assessment-2026-07-12.json", data: string(files[completenessDir+"delivery-assessment-2026-10-31.json"].Data)},
		"comparison extra member":   {path: comparisonDir + "reference-v1.json", data: v1[:len(v1)-2] + `,"extra":1}`},
		"comparison literal":        {path: comparisonDir + "reference-v1.json", data: replace(v1, "owner-shape-projection/v1", "other/v1")},
		"comparison missing rule":   {path: comparisonDir + "reference-v1.json", data: replace(v1, `"scenario-import": "1"`, `"scenario-import-x": "1"`)},
		"comparison rule version":   {path: comparisonDir + "reference-v1.json", data: replace(v1, `"scenario-import": "1"`, `"scenario-import": "2"`)},
		"comparison revision two":   {path: comparisonDir + "reference-v1.json", data: replace(v1, `"module": "1"`, `"module": "2"`)},
		"comparison limit bound":    {path: comparisonDir + "reference-v1.json", data: replace(v1, `"max_path_depth": 8`, `"max_path_depth": 33`)},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			damagedFiles := maps.Clone(files)
			if tc.data == "" {
				delete(damagedFiles, tc.path)
			} else {
				damagedFiles[tc.path] = &fstest.MapFile{Data: []byte(tc.data)}
			}
			_, err := load(damagedFiles, schemas(t))
			if category, _ := faultCode(err); category != fault.Operational {
				t.Errorf("load() error = %v, want an Operational fault", err)
			}
		})
	}
}

func replace(text, old, replacement string) string { return strings.Replace(text, old, replacement, 1) }

func TestComparisonProfilesMatchTheReferenceDigests(t *testing.T) {
	p := mustLoad(t)
	for name, digest := range map[string]string{
		"reference-v1": "sha256:50e5183320de75ccb96ded6d709b6c03e351850633a976cba21d281455749e36",
		"reference-v2": "sha256:6c854fccb0a982dff1bb122ba75d795a3f2a28474c0cd7be0022137830fc7830",
	} {
		profile, err := p.ComparisonProfile(name)
		if err != nil || profile.Digest != digest || profile.Limits != (ComparisonLimits{4096, 8192, 8, 1024, 64}) {
			t.Errorf("ComparisonProfile(%q) = %s %+v, %v; want digest %s", name, profile.Digest, profile.Limits, err, digest)
		}
	}
	if _, err := p.ComparisonProfile("reference-v3"); err == nil {
		t.Errorf("ComparisonProfile(reference-v3) error = nil, want NotFound")
	}
	if limits, ok := comparisonLimits(nil); !ok || limits != (ComparisonLimits{4096, 8192, 8, 1024, 64}) {
		t.Errorf("comparisonLimits(nil) = %+v, %t, want the published defaults", limits, ok)
	}
}

func TestRelationProfileLookupIsExact(t *testing.T) {
	p := mustLoad(t)
	if diff := cmp.Diff(relationProfileIDs(), p.RelationProfileIDs()); diff != "" {
		t.Errorf("RelationProfileIDs() mismatch (-want +got):\n%s", diff)
	}
	crossing, err := p.RelationProfile("participant-crossing-dpbb-finite-v1", "rev2")
	if err != nil || crossing.ParameterKind != CrossingKind || crossing.RightCarrierRef == "" || crossing.TaxonomyRevision != "rev8" {
		t.Errorf("RelationProfile(crossing) = %+v, %v; want the rev2 crossing profile", crossing, err)
	}
	if _, err := p.RelationProfile("participant-opacity-baseline-v1", "sem-231/rev2"); err != nil {
		t.Errorf("RelationProfile(history) error = %v, want nil", err)
	}
	for _, tc := range [][2]string{
		{"participant-opacity-baseline-v1", "sem-231/rev1"},
		{"unknown-profile", "rev1"},
		{"Participant-Opacity-Baseline-V1", "sem-231/rev2"},
		{"../participant-opacity-baseline-v1", "sem-231/rev2"},
	} {
		_, err := p.RelationProfile(tc[0], tc[1])
		if category, code := faultCode(err); category != fault.NotFound || code != "behavioral-authority-unsupported" {
			t.Errorf("RelationProfile(%q, %q) error = %v, want NotFound behavioral-authority-unsupported", tc[0], tc[1], err)
		}
	}
}

func TestValidationProfileSelection(t *testing.T) {
	p := mustLoad(t)
	catalog := p.ValidationCatalog()
	if catalog.Version == "" || len(catalog.Profiles) == 0 || len(catalog.Strengths) == 0 {
		t.Fatalf("ValidationCatalog() = %+v, want the packaged catalog", catalog)
	}
	first := catalog.Profiles[0]
	selected, err := p.SelectValidationProfile(first.ID, first.Version, first.SubjectKinds[0])
	if err != nil || selected.ID != first.ID {
		t.Errorf("SelectValidationProfile(%s) = %+v, %v", first.ID, selected, err)
	}
	selected.SubjectKinds[0] = "changed"
	if p.ValidationCatalog().Profiles[0].SubjectKinds[0] == "changed" {
		t.Errorf("SelectValidationProfile() shares state with the catalog")
	}
	for name, tc := range map[string]struct{ id, version, subject, code string }{
		"unknown subject": {first.ID, first.Version, "undeclared-subject", "validation-profile-subject-undeclared"},
		"unknown version": {first.ID, "v99", first.SubjectKinds[0], "validation-profile-unknown"},
		"unknown id":      {"unknown-profile", first.Version, first.SubjectKinds[0], "validation-profile-unknown"},
	} {
		_, err := p.SelectValidationProfile(tc.id, tc.version, tc.subject)
		if category, code := faultCode(err); category != fault.InvalidInput || code != tc.code {
			t.Errorf("%s: SelectValidationProfile() error = %v, want InvalidInput %s", name, err, tc.code)
		}
	}
}
