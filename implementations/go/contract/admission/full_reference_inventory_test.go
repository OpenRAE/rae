package admission

import (
	"encoding/json"
	"io/fs"
	"slices"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestFullReferenceFixtureInventorySeparatesNativeSemanticVectors(t *testing.T) {
	source := fstest.MapFS{}
	for _, path := range []string{
		"fixtures/sdl/semantic-vectors-v1/semantics.json",
		"fixtures/sdl/semantic-vectors-v1/semantics-999.json",
		"fixtures/sdl/semantic-vectors-v10/example.json",
		"fixtures/sdl/semantic-vectors-v1.json",
		"fixtures/example-v1/positive.json",
	} {
		source[path] = &fstest.MapFile{Data: []byte(`{}`)}
	}
	contracts, other := completeFixturePaths(t, source, map[string]bool{"example-v1": true}, nil)
	if !slices.Equal(contracts, []string{"fixtures/example-v1/positive.json"}) ||
		!slices.Equal(other, []string{"fixtures/sdl/semantic-vectors-v1.json", "fixtures/sdl/semantic-vectors-v10/example.json"}) {
		t.Fatalf("unexpected fixture ownership: contracts=%v other=%v", contracts, other)
	}
}

// Inventory comes from all packaged fixture files and the published registry,
// independent of the smaller CLI admission corpus and the reference table.
// nativeOwnerFixture records the Python verdict for a contract fixture whose Go
// admission needs a native SDL owner callback. The named native test owns its
// complete result; this package checks only that the fixture is accounted for.
type nativeOwnerFixture struct {
	Contract        string `json:"contract_id"`
	InputDigest     string `json:"input_sha256"`
	PublishedSchema bool   `json:"published_schema_admitted"`
	Full            bool   `json:"full_admitted"`
	Failure         string `json:"failure_class"`
	Check           string `json:"reference_check"`
	CoveredBy       string `json:"covered_by"`
}

// splitNativeOwnerFixtures removes natively covered fixtures from the scanned
// contract inventory. Each one must still be a packaged contract fixture.
func splitNativeOwnerFixtures(t *testing.T, source fs.FS, contracts []string, native map[string]nativeOwnerFixture) []string {
	t.Helper()
	remaining := slices.Clone(contracts)
	for path, fixture := range native {
		index := slices.Index(remaining, path)
		if index < 0 || fixture.Contract == "" || fixture.Check == "" || fixture.CoveredBy == "" {
			t.Fatal("stale or incomplete native owner fixture:", path)
		}
		raw, err := fs.ReadFile(source, path)
		if err != nil {
			t.Fatal(err)
		}
		if digest.SHA256(raw) != fixture.InputDigest {
			t.Fatal("native owner fixture differs from its recorded bytes:", path)
		}
		remaining = slices.Delete(remaining, index, index+1)
	}
	return remaining
}

func checkCompleteFixtureInventory(t *testing.T, source fs.FS, cases []fullReferenceCase, inventory []string, other map[string]string, native map[string]nativeOwnerFixture) {
	t.Helper()
	entries, err := fs.ReadDir(source, "schema-publication/entries")
	if err != nil {
		t.Fatal(err)
	}
	ids := map[string]bool{}
	for _, entry := range entries {
		ids[strings.TrimSuffix(entry.Name(), ".json")] = true
	}
	versions := fixtureVersionIndex(t, source, entries)
	contracts, noncontracts := completeFixturePaths(t, source, ids, versions)
	contracts = splitNativeOwnerFixtures(t, source, contracts, native)
	if !slices.Equal(contracts, inventory) {
		t.Fatalf("full reference does not cover complete contract fixture inventory: scanned=%d recorded=%d first difference=%v", len(contracts), len(inventory), firstFixtureDifference(contracts, inventory))
	}
	excluded := make([]string, 0, len(other))
	for path, reason := range other {
		if reason == "" {
			t.Fatal("unclassified fixture")
		}
		excluded = append(excluded, path)
	}
	slices.Sort(excluded)
	if !slices.Equal(excluded, noncontracts) {
		t.Fatal("full reference does not classify every other-surface fixture")
	}
	checkFullReferenceRows(t, cases, contracts, ids)
}
func checkFullReferenceRows(t *testing.T, cases []fullReferenceCase, contracts []string, ids map[string]bool) {
	t.Helper()
	covered := map[string]bool{}
	names := map[string]bool{}
	selectors := 0
	for _, c := range cases {
		if names[c.Name] || c.Check == "" || c.Owner == "" {
			t.Fatal("duplicate or incomplete full reference row")
		}
		names[c.Name] = true
		if !ids[c.Contract] {
			selectors++
			continue
		}
		if covered[c.InputPath] {
			t.Fatal("duplicate fixture input")
		}
		covered[c.InputPath] = true
	}
	paths := make([]string, 0, len(covered))
	for path := range covered {
		paths = append(paths, path)
	}
	slices.Sort(paths)
	if !slices.Equal(paths, contracts) || selectors != 1 {
		t.Fatal("full validation cases omit a fixture or selector regression")
	}
}

func completeFixturePaths(t *testing.T, source fs.FS, ids map[string]bool, versions map[string]string) ([]string, []string) {
	t.Helper()
	var contracts, other []string
	err := fs.WalkDir(source, "fixtures", func(path string, entry fs.DirEntry, err error) error {
		switch {
		case err != nil:
			return err
		// Native SDL tests own this family's complete inventory and results.
		case entry.IsDir() && path == "fixtures/sdl/semantic-vectors-v1":
			return fs.SkipDir
		case entry.IsDir() || !strings.HasSuffix(path, ".json"):
			return nil
		}
		contract := false
		for part := range strings.SplitSeq(path, "/") {
			contract = contract || ids[part]
		}
		if !contract {
			contract = fixtureHasPublishedVersion(t, source, path, versions)
		}
		if contract {
			contracts = append(contracts, path)
		} else {
			other = append(other, path)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	slices.Sort(contracts)
	slices.Sort(other)
	return contracts, other
}

func fixtureVersionIndex(t *testing.T, source fs.FS, entries []fs.DirEntry) map[string]string {
	t.Helper()
	candidates := map[string][]string{}
	for _, entry := range entries {
		raw, err := fs.ReadFile(source, "schema-publication/entries/"+entry.Name())
		if err != nil {
			t.Fatal(err)
		}
		var publication struct {
			ID   string `json:"contract_id"`
			Path string `json:"schema_path"`
		}
		if err = json.Unmarshal(raw, &publication); err != nil {
			t.Fatal(err)
		}
		raw, err = fs.ReadFile(source, strings.TrimPrefix(publication.Path, "contracts/"))
		if err != nil {
			t.Fatal(err)
		}
		var schema struct {
			Properties map[string]struct {
				Const any `json:"const"`
			} `json:"properties"`
		}
		if err = json.Unmarshal(raw, &schema); err != nil {
			t.Fatal(err)
		}
		if version, ok := schema.Properties["schema_version"].Const.(string); ok {
			candidates[version] = append(candidates[version], publication.ID)
		}
	}
	result := map[string]string{}
	for version, ids := range candidates {
		if len(ids) == 1 {
			result[version] = ids[0]
		}
	}
	return result
}
func fixtureHasPublishedVersion(t *testing.T, source fs.FS, path string, versions map[string]string) bool {
	t.Helper()
	raw, err := fs.ReadFile(source, path)
	if err != nil {
		t.Fatal(err)
	}
	var value struct {
		Version string `json:"schema_version"`
	}
	return json.Unmarshal(raw, &value) == nil && versions[value.Version] != ""
}

func firstFixtureDifference(a, b []string) string {
	for index := range min(len(a), len(b)) {
		if a[index] != b[index] {
			return a[index] + " / " + b[index]
		}
	}
	return "length differs"
}
