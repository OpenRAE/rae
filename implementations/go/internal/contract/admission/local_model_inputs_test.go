package admission

import (
	"bytes"
	"compress/gzip"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"strings"
	"sync"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

type localModelInputCase struct {
	Contract               string            `json:"contract"`
	CaseFile               string            `json:"case_file"`
	InputSHA               string            `json:"input_sha256"`
	Admitted               bool              `json:"admitted"`
	Name                   string            `json:"name"`
	Changes                []referenceChange `json:"changes"`
	PublishedTypeAdmitted  *bool             `json:"published_type_admitted"`
	LocalSemanticsAdmitted *bool             `json:"local_semantics_admitted"`
}

// These are model-stage comparisons. Full-admission tests separately exercise
// trusted external owners; a local model verdict cannot grant their authority.
func TestRecordedLocalModelsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []localModelInputCase `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/local-model-inputs.json", &reference)
	if len(reference.Cases) != 581 {
		t.Fatal("local model input inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Contract+"/"+c.InputSHA, func(t *testing.T) {
			checkRecordedLocalModelCase(t, e, c)
		})
	}
}

func TestAdditionalContractModelsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []localModelInputCase `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/expanded-model-inputs.json", &reference)
	if len(reference.Cases) != 1049 {
		t.Fatal("additional model inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Contract+"/"+c.InputSHA, func(t *testing.T) { checkRecordedLocalModelCase(t, e, c) })
	}
}

func TestDiverseContractModelsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	runModelReferenceShards(t, "diverse-model-inputs", 1760, 5)
}

func TestLocalModelBoundaryChangesMatchPython(t *testing.T) {
	t.Parallel()
	runModelReferenceShards(t, "local-model-boundaries", 1357, 4)
}

func TestAdditionalModelBoundariesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	runModelReferenceShards(t, "expanded-model-boundaries", 1346, 4)
}

func checkRecordedLocalModelCase(t *testing.T, e *Validator, c localModelInputCase) {
	t.Helper()
	raw := retainedModelInput(t, c)
	if len(c.Changes) > 0 {
		root := decodeRuleObject(t, string(raw))
		for _, change := range c.Changes {
			applyReferenceChange(t, root, change)
		}
		raw = controlJSON(t, root)
	}
	key := [2]string{c.Contract, digest.SHA256(raw)}
	evaluate := sync.OnceValue(func() error { return referenceModelResult(e, c.Contract, raw) })
	cached, _ := sharedReferenceModelResults.LoadOrStore(key, evaluate)
	cachedEvaluation, ok := cached.(func() error)
	if !ok {
		t.Fatal("invalid shared reference evaluation")
	}
	err := cachedEvaluation()

	expected := c.Admitted
	if c.LocalSemanticsAdmitted != nil {
		expected = *c.LocalSemanticsAdmitted
	}
	if c.PublishedTypeAdmitted != nil {
		if c.Contract != termExperimentBindingDescriptorsV1 || c.Admitted || !*c.PublishedTypeAdmitted {
			t.Fatal("unexpected published integer-type exception")
		}
		expected = *c.PublishedTypeAdmitted
	}
	if (err == nil) != expected {
		t.Fatalf("local model result differs (expected=%v, Python=%v): %v", expected, c.Admitted, err)
	}
}

func retainedModelInput(t *testing.T, c localModelInputCase) []byte {
	t.Helper()
	if !strings.HasPrefix(c.CaseFile, "cases/schema/validate/") || strings.Contains(c.CaseFile, "..") {
		t.Fatal("unsafe original case path")
	}
	var original struct {
		Args  []string          `json:"args"`
		Files map[string]string `json:"files"`
	}
	readFullReferenceJSON(t, "testdata/retained-model-inputs/"+c.CaseFile, &original)
	if len(original.Args) != 1 || original.Args[0] != c.Contract || original.Files["payload.json"] != "sha256:"+c.InputSHA {
		t.Fatal("model input differs from its original corpus case")
	}
	read := sync.OnceValue(func() []byte { return retainedParityBlob(t, c.InputSHA) })
	cached, _ := sharedRetainedModelBytes.LoadOrStore(c.InputSHA, read)
	load, ok := cached.(func() []byte)
	if !ok {
		t.Fatal("invalid retained model input cache")
	}
	return bytes.Clone(load())
}

var sharedRetainedModelBytes sync.Map //nolint:gochecknoglobals // Immutable independently recorded baseline bytes; return copies while inflating each retained blob once across parallel reference groups.

// Keep independently recorded model inputs with their owner: parity snapshots
// can be regenerated without changing these baselines. This reader retains
// the original bounded v2 format; parity imports admission, so its loader
// cannot be imported by an in-package test.
func retainedParityBlob(t *testing.T, identity string) []byte {
	t.Helper()
	if decoded, err := hex.DecodeString(identity); err != nil || len(decoded) != 32 || strings.ToLower(identity) != identity {
		t.Fatal("invalid retained blob identity")
	}
	root := "testdata/retained-model-inputs/"
	data, err := fs.ReadFile(os.DirFS(root), "inputs/"+identity)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.HasPrefix(data, []byte{0x1f, 0x8b}) {
		data = retainedParityPieces(t, root, identity, data)
	}
	reader, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	raw, readErr := io.ReadAll(io.LimitReader(reader, 64*1048576+1))
	closeErr := reader.Close()
	if readErr != nil || closeErr != nil || len(raw) > 64*1048576 || digest.SHA256(raw) != "sha256:"+identity {
		t.Fatal("retained input is oversized, corrupt or has changed bytes")
	}
	return raw
}

func retainedParityPieces(t *testing.T, root, identity string, index []byte) []byte {
	t.Helper()
	var entry struct {
		Parts int `json:"parts"`
	}
	if err := json.Unmarshal(index, &entry); err != nil || entry.Parts < 1 || entry.Parts > 512 {
		t.Fatal("invalid retained piece inventory")
	}
	var data bytes.Buffer
	for n := range entry.Parts {
		piece, err := fs.ReadFile(os.DirFS(root), fmt.Sprintf("pieces/%s/%d", identity, n))
		if err != nil || len(piece) < 1 || piece[0] != 0 || len(piece) > 256*1024+1 {
			t.Fatal("invalid retained blob piece")
		}
		data.Write(piece[1:])
	}
	return data.Bytes()
}

// Distinct reference records can contain identical contract/input bytes. Run
// each unique input once, while every row still checks its own recorded verdict.
var sharedReferenceModelResults sync.Map //nolint:gochecknoglobals // Immutable per-input results with once-only evaluation; concurrent reference groups share the same production validator.

func referenceModelResult(e *Validator, id string, raw []byte) error {
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	raw, err := e.prepare(id, raw, limits)
	if err == nil {
		err = e.low.CheckLocal(id, raw, limits)
	}
	if err == nil {
		err = e.checkModels(id, raw, limits)
	}
	if err == nil && sdlPhaseContract(id) {
		err = e.checkSDLPhase(id, raw, limits, recordedSDLPhaseOwner{})
	}
	return err
}

func runModelReferenceShards(t *testing.T, prefix string, expectedCount, expectedFiles int) {
	t.Helper()
	var reference struct {
		Count int      `json:"case_count"`
		Files []string `json:"case_files"`
	}
	readFullReferenceJSON(t, "testdata/"+prefix+".json", &reference)
	if reference.Count != expectedCount || len(reference.Files) != expectedFiles {
		t.Fatal("model reference inventory changed")
	}
	e := boundTestOwner(t)
	count := 0
	for index, file := range reference.Files {
		if file != fmt.Sprintf("%s-%02d.json", prefix, index+1) {
			t.Fatal("unexpected model reference shard")
		}
		var cases []localModelInputCase
		readFullReferenceJSON(t, "testdata/"+file, &cases)
		for _, c := range cases {
			name := c.Contract + "/" + c.InputSHA
			if c.Name != "" {
				name += "/" + c.Name
			}
			t.Run(name, func(t *testing.T) { checkRecordedLocalModelCase(t, e, c) })
		}
		count += len(cases)
	}
	if count != reference.Count {
		t.Fatal("model reference cases missing")
	}
}
