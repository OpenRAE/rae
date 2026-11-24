package concept

import (
	"encoding/json"
	"errors"
	"io/fs"
	"maps"
	"sync"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
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

func mustLoad(t *testing.T) *Authority {
	t.Helper()
	a, err := Load(schemas(t))
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	return a
}

func TestLoadReadsEveryPackagedDocument(t *testing.T) {
	a := mustLoad(t)
	documents := a.Documents()
	if len(documents) != 16 {
		t.Fatalf("len(Documents()) = %d, want 16", len(documents))
	}
	for i, document := range documents {
		if document.ContractID == "" || len(document.JSON) == 0 {
			t.Errorf("Documents()[%d] = %q with %d bytes, want a contract and content", i, document.Path, len(document.JSON))
		}
		if i > 0 && documents[i-1].Path >= document.Path {
			t.Errorf("Documents() path %q follows %q, want path order", document.Path, documents[i-1].Path)
		}
	}
	documents[0].JSON[0] = 'x'
	documents[0].Path = "changed"
	if again := a.Documents(); again[0].JSON[0] != '{' || again[0].Path == "changed" {
		t.Errorf("Documents() shares state with an earlier result")
	}
	if _, err := Load(nil); err == nil {
		t.Errorf("Load(nil) error = nil, want refusal")
	}
}

func TestLoadRefusesDamagedDocuments(t *testing.T) {
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
	if _, err := load(files, schemas(t)); err != nil {
		t.Fatalf("load(packaged copy) error = %v", err)
	}
	cases := map[string]struct {
		path string
		data string
	}{
		"missing document":          {path: pathFamilies},
		"schema failure":            {path: pathFamilies, data: `{"schema_version":"concept-families/v1"}`},
		"duplicate member":          {path: pathFamilies, data: `{"schema_version":"concept-families/v1","schema_version":"concept-families/v1"}`},
		"history revision mismatch": {path: relationHistoryDir + "rev9.json", data: string(files[relationHistoryDir+"rev8.json"].Data)},
		"repeated scope":            {path: pathVocabularies, data: repeatedScopeCatalog(t, files[pathVocabularies].Data)},
		"bad extension pattern":     {path: pathVocabularies, data: badPatternCatalog(t, files[pathVocabularies].Data)},
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
			if category, ok := fault.CategoryOf(err); !ok || category != fault.Operational {
				t.Errorf("load() error = %v, want an Operational fault", err)
			}
		})
	}
}

func TestVocabulariesMatchTheReference(t *testing.T) {
	a := mustLoad(t)
	for _, tc := range []struct {
		vocabulary, term string
		want             bool
	}{
		{"provisioner-node-types", "x-acme:bare-metal", true},
		{"provisioner-node-types", "bare-metal", false},
		{"orchestrator-supported-sections", "x-acme:custom-stage", true},
		{"orchestrator-supported-sections", "custom-stage", false},
		{"participant-decision-surface-modes", "x-acme:swarm-control", true},
		{"participant-decision-surface-modes", "swarm-control", false},
		{"participant-decision-surface-modes", "x-acme:swarm-control\n", false},
		{"participant-offensive-behavior-activities", "defense-impairment", true},
		{"participant-offensive-behavior-activities", "defense-evasion", false},
		{"participant-offensive-behavior-activities", "ai-model-access", false},
		{"participant-offensive-behavior-activities", "continuous-monitoring", false},
		{"participant-ai-offensive-behavior-activities", "defense-evasion", true},
		{"participant-ai-offensive-behavior-activities", "defense-impairment", false},
		{"participant-defensive-behavior-activities", "incident-mitigation", true},
		{"participant-defensive-behavior-activities", "reconnaissance", false},
		{"participant-defensive-behavior-activities", "unregistered-activity", false},
		{"realization-support-modes", "x-acme:custom-mode", false},
		{"realization-support-modes", "constrained", true},
		{"unknown-vocabulary", "anything", false},
	} {
		if got := a.Permits(tc.vocabulary, tc.term); got != tc.want {
			t.Errorf("Permits(%q, %q) = %t, want %t", tc.vocabulary, tc.term, got, tc.want)
		}
	}
	closed, ok := a.Vocabulary("processor-features")
	want := []string{"compilation", "dependency-ordering", "evaluation-coordination", "objective-window-consistency", "orchestration-coordination", "planning", "runtime-control-plane", "workflow-semantics"}
	if !ok || closed.ExtensionPolicy != closedPolicy || closed.ExtensionPattern != "" || !cmp.Equal(closed.Terms, want) {
		t.Errorf("Vocabulary(processor-features) = %+v, %t, want closed terms %v", closed, ok, want)
	}
	closed.Terms[0] = "changed"
	if again, _ := a.Vocabulary("processor-features"); again.Terms[0] != "compilation" {
		t.Errorf("Vocabulary() shares its terms with an earlier result")
	}
}

func TestScopeChecksMatchTheReference(t *testing.T) {
	a := mustLoad(t)
	if v, ok := a.ScopeVocabulary("behavior_specifications.behavior_mode"); !ok || v.ID != "participant-decision-surface-modes" {
		t.Errorf("ScopeVocabulary(behavior_mode) = %q, %t, want participant-decision-surface-modes", v.ID, ok)
	}
	if _, ok := a.ScopeVocabulary("ungoverned.scope"); ok {
		t.Errorf("ScopeVocabulary(ungoverned.scope) found a vocabulary, want none")
	}
	if err := a.CheckScope("behavior_specifications.behavior_mode", "autonomous", "human-supervised", "x-acme:swarm-control"); err != nil {
		t.Errorf("CheckScope(governed values) error = %v, want nil", err)
	}
	for name, tc := range map[string]struct {
		scope, value, code string
	}{
		"unpermitted": {"behavior_specifications.behavior_mode", "swarm-control", "vocabulary-term-unpermitted"},
		"ungoverned":  {"ungoverned.scope", "anything", "vocabulary-scope-ungoverned"},
	} {
		err := a.CheckScope(tc.scope, tc.value)
		var typed *fault.Error
		if !errors.As(err, &typed) || typed.Category() != fault.InvalidInput || typed.Code() != tc.code {
			t.Errorf("%s: CheckScope() error = %v, want InvalidInput %s", name, err, tc.code)
		}
	}
}

func TestFamiliesKeepAuthorityAndProvenance(t *testing.T) {
	a := mustLoad(t)
	if f, ok := a.Family("assets"); !ok || f != (Family{ID: "assets", Authority: "UCO", Provenance: "adopted"}) {
		t.Errorf("Family(assets) = %+v, %t, want UCO adopted", f, ok)
	}
	if _, ok := a.Family("unknown-family"); ok {
		t.Errorf("Family(unknown-family) found a family, want none")
	}
}

func TestRelationRevisionsAreExact(t *testing.T) {
	a := mustLoad(t)
	current := a.CurrentRelationCatalog()
	if current.TaxonomyID != "raes-behavioral-relations" || current.TaxonomyRevision != "rev14" {
		t.Errorf("CurrentRelationCatalog() = %s %s, want raes-behavioral-relations rev14", current.TaxonomyID, current.TaxonomyRevision)
	}
	for _, revision := range append([]string{"rev14"}, historyRevisions()...) {
		catalog, err := a.RelationCatalog(revision)
		if err != nil || catalog.TaxonomyRevision != revision || len(catalog.Relations) == 0 {
			t.Errorf("RelationCatalog(%q) = %s with %d relations, %v; want that revision", revision, catalog.TaxonomyRevision, len(catalog.Relations), err)
		}
	}
	for _, revision := range []string{"rev7", "rev15", "", "REV14"} {
		_, err := a.RelationCatalog(revision)
		if category, ok := fault.CategoryOf(err); !ok || category != fault.NotFound {
			t.Errorf("RelationCatalog(%q) error = %v, want a NotFound fault", revision, err)
		}
	}
	relation, ok := current.Relation("divergence-preserving-branching-bisimulation")
	if !ok || !relation.ProjectionRequired || !relation.ProfileRequired {
		t.Errorf("Relation(dpbb) = %+v, %t, want projection and profile required", relation, ok)
	}
	if _, ok := current.Relation("unknown-relation"); ok {
		t.Errorf("Relation(unknown-relation) found a relation, want none")
	}
	current.Relations[0].ID = "changed"
	if again := a.CurrentRelationCatalog(); again.Relations[0].ID == "changed" {
		t.Errorf("CurrentRelationCatalog() shares its relations with an earlier result")
	}
}

func TestPinnedSnapshotsKeepTheirSourcePins(t *testing.T) {
	a := mustLoad(t)
	var got []SchemeSnapshot
	for _, s := range a.PinnedSnapshots() {
		got = append(got, SchemeSnapshot{SchemeID: s.SchemeID, Authority: s.Authority, Revision: s.Revision, SourceDigest: s.SourceDigest, Concepts: s.Concepts[:1]})
	}
	want := []SchemeSnapshot{
		{SchemeID: "fipa-communicative-act-library", Authority: "Foundation for Intelligent Physical Agents", Revision: "SC00037J-2002-12-03", SourceDigest: "sha256:90b3277247ef7e7f614ba4c0d58fb2b86aa53ff69036d27a731c09a26c605227", Concepts: []SnapshotTerm{{ConceptID: "accept-proposal", Status: "current"}}},
		{SchemeID: "mitre-atlas-tactics", Authority: "MITRE ATLAS", Revision: "2026.06", SourceDigest: "sha256:b771de8b1489564b2838a709c7429849a9575dbd94073928817fe1a21661e70a", Concepts: []SnapshotTerm{{ConceptID: "AML.TA0002", Status: "current"}}},
		{SchemeID: "mitre-attack-enterprise-tactics", Authority: "MITRE ATT&CK", Revision: "v19.1", SourceDigest: "sha256:bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3", Concepts: []SnapshotTerm{{ConceptID: "TA0043", Status: "current"}}},
		{SchemeID: "nist-csf-defensive-categories", Authority: "NIST Cybersecurity Framework", Revision: "2.0", SourceDigest: "sha256:014492980e87f8ce2c98d80ea040540392de96a08980c2f9901114ad4108b2c3", Concepts: []SnapshotTerm{{ConceptID: "DE.CM", Status: "current"}}},
		{SchemeID: "w3c-activitystreams-activity-types", Authority: "World Wide Web Consortium", Revision: "REC-activitystreams-vocabulary-20170523", SourceDigest: "sha256:1418443392160f4bb23dffb5727f5216d1f56d3430377dc67d364016521401db", Concepts: []SnapshotTerm{{ConceptID: "https://www.w3.org/ns/activitystreams#Accept", Status: "current"}}},
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("PinnedSnapshots() mismatch (-want +got):\n%s", diff)
	}
	counts := map[string]int{}
	for _, s := range a.PinnedSnapshots() {
		counts[s.SchemeID] = len(s.Concepts)
	}
	if diff := cmp.Diff(map[string]int{"fipa-communicative-act-library": 22, "mitre-atlas-tactics": 16, "mitre-attack-enterprise-tactics": 15, "nist-csf-defensive-categories": 8, "w3c-activitystreams-activity-types": 28}, counts); diff != "" {
		t.Errorf("PinnedSnapshots() term counts mismatch (-want +got):\n%s", diff)
	}
}

func mutateVocabularies(t *testing.T, data []byte, change func(map[string]any)) string {
	t.Helper()
	var catalog map[string]any
	if err := json.Unmarshal(data, &catalog); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	vocabularies, ok := catalog["vocabularies"].(map[string]any)
	if !ok {
		t.Fatal("the catalog has no vocabularies")
	}
	change(vocabularies)
	out, err := json.Marshal(catalog)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	return string(out)
}

func repeatedScopeCatalog(t *testing.T, data []byte) string {
	t.Helper()
	return mutateVocabularies(t, data, func(v map[string]any) {
		modes, _ := v["participant-decision-surface-modes"].(map[string]any)
		scopes, _ := modes["governed_scopes"].([]any)
		modes["governed_scopes"] = append(scopes, "implementation_kind")
	})
}

func badPatternCatalog(t *testing.T, data []byte) string {
	t.Helper()
	return mutateVocabularies(t, data, func(v map[string]any) {
		modes, _ := v["participant-decision-surface-modes"].(map[string]any)
		modes["extension_pattern"] = "^(?=x-)x-a:b$"
	})
}
