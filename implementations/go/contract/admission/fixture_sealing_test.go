package admission

import (
	"encoding/json"
	"io/fs"
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// The reference engine sealed every valid and context-invalid fixture of a
// contract with derived fields. The native sealer must produce the same
// canonical document.
func TestFixtureSealingMatchesReferenceEngine(t *testing.T) {
	var reference struct {
		Specification string            `json:"specification"`
		Contracts     []string          `json:"contracts"`
		Kinds         []string          `json:"kinds"`
		Digests       map[string]string `json:"sealed_fixture_digests"`
	}
	readFullReferenceJSON(t, "testdata/contract-seal-reference.json", &reference)
	if reference.Specification != "raes-contract-seal-reference/v1" || !slices.Equal(reference.Kinds, []string{fixtureKindContextInvalid, fixtureKindValid}) {
		t.Fatal("unknown contract seal reference")
	}
	contracts := slices.Clone(sealedContracts())
	slices.Sort(contracts)
	if !slices.Equal(reference.Contracts, contracts) {
		t.Fatalf("sealed contracts differ from the reference: %v", reference.Contracts)
	}
	source, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	seen := 0
	err = fs.WalkDir(source, "fixtures", func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil || entry.IsDir() || !strings.HasSuffix(path, ".json") {
			return walkErr
		}
		parts := strings.Split(path, "/")
		if len(parts) != 5 || !slices.Contains(contracts, parts[2]) || !slices.Contains(reference.Kinds, parts[3]) {
			return nil
		}
		seen++
		expected, ok := reference.Digests[path]
		if !ok {
			t.Errorf("%s: no reference seal", path)
			return nil
		}
		raw, readErr := fs.ReadFile(source, path)
		if readErr != nil {
			return readErr
		}
		sealed, sealErr := SealFixture(e, parts[2], parts[3], raw, limits)
		if sealErr != nil {
			t.Errorf("%s: %v", path, sealErr)
			return nil
		}
		var value any
		if decodeErr := json.Unmarshal(sealed, &value); decodeErr != nil {
			t.Errorf("%s: sealed bytes are not JSON: %v", path, decodeErr)
			return nil
		}
		actual, digestErr := jsonDigest(value)
		if digestErr != nil || actual != expected {
			t.Errorf("%s: sealed digest %s, reference %s", path, actual, expected)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if seen != len(reference.Digests) {
		t.Fatalf("sealed fixture inventory differs: native=%d reference=%d", seen, len(reference.Digests))
	}
}

func TestFixtureSealingKeepsPresentValuesAndOtherKinds(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}
	raw := []byte(`{"z":1,"configuration_digest":"sha256:` + strings.Repeat("a", 64) + `"}`)
	for _, kind := range []string{"invalid", fixtureKindValid} {
		sealed, err := SealFixture(e, "participant-configuration-result-v1", kind, raw, limits)
		if err != nil || string(sealed) != string(raw) {
			t.Fatalf("%s: sealing changed a present value or an unsealed kind: %s %v", kind, sealed, err)
		}
	}
	sealed, err := SealFixture(e, "unknown-contract-v1", fixtureKindValid, raw, limits)
	if err != nil || string(sealed) != string(raw) {
		t.Fatal("sealing changed a document without derived fields")
	}
}

func TestInsertMembersKeepsOriginalBytesAndOrder(t *testing.T) {
	raw := []byte(`{"b":[{},{"x":1.50}],"a":{"":"k"},"c":{}}`)
	fills := map[string][]sealedMember{
		"/b/0": {{"d", "one"}},
		"/b/1": {{"d", "two"}, {"e", "three"}},
		"/a":   {{"d", "four"}},
		"":     {{"z", "five"}},
	}
	actual, err := insertMembers(raw, fills)
	want := `{"b":[{"d":"one"},{"x":1.50,"d":"two","e":"three"}],"a":{"":"k","d":"four"},"c":{},"z":"five"}`
	if err != nil || string(actual) != want {
		t.Fatalf("insertMembers = %s, %v", actual, err)
	}
	if _, err := insertMembers(raw, map[string][]sealedMember{"/missing": {{"d", "x"}}}); err == nil {
		t.Fatal("insertMembers accepted an absent owner")
	}
}
