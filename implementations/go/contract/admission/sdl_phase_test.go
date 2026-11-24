package admission

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"maps"
	"os"
	"slices"
	"strings"
	"sync"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type sdlPhaseReference struct {
	ContractID     string          `json:"contract_id"`
	SourceSHA256   string          `json:"source_sha256"`
	SchemaAdmitted bool            `json:"published_schema_admitted"`
	ModelAdmitted  bool            `json:"python_model_admitted"`
	Document       json.RawMessage `json:"document"`
}

// Immutable independent phase records are shared; each callback returns a copy.
var sharedSDLPhaseRecords = sync.OnceValues(readSDLPhaseRecords) //nolint:gochecknoglobals // Fixed source-bound native model records; callbacks cannot mutate the shared documents.

func readSDLPhaseRecords() (map[string]sdlPhaseReference, error) {
	root := os.DirFS("testdata")
	data, err := fs.ReadFile(root, "sdl-phase-verdicts.json")
	if err != nil {
		return nil, err
	}
	var index struct {
		Count int               `json:"case_count"`
		Files map[string]string `json:"case_files"`
	}
	if err := json.Unmarshal(data, &index); err != nil {
		return nil, err
	}
	records := map[string]sdlPhaseReference{}
	for number, name := range slices.Sorted(maps.Keys(index.Files)) {
		if name != fmt.Sprintf("sdl-phase-verdicts-%02d.json", number+1) {
			return nil, errors.New("unexpected SDL phase shard")
		}
		rows, err := readSDLPhaseShard(root, name, index.Files[name])
		if err != nil {
			return nil, err
		}
		for _, row := range rows {
			if _, exists := records[row.SourceSHA256]; exists || !sdlPhaseContract(row.ContractID) {
				return nil, errors.New("duplicate or unknown SDL phase record")
			}
			records[row.SourceSHA256] = row
		}
	}
	if index.Count != 332 || len(records) != index.Count {
		return nil, errors.New("SDL phase reference inventory changed")
	}
	return records, nil
}

func readSDLPhaseShard(root fs.FS, name, commitment string) ([]sdlPhaseReference, error) {
	data, err := fs.ReadFile(root, name)
	if err != nil || len(data) > 512*1024 || digest.SHA256(data) != commitment {
		return nil, errors.New("SDL phase reference shard changed")
	}
	var rows []sdlPhaseReference
	if err := json.Unmarshal(data, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

type recordedSDLPhaseOwner struct{}

func (recordedSDLPhaseOwner) AdmitSDLPhase(request SDLPhaseRequest) (SDLPhaseAdmission, error) {
	records, err := sharedSDLPhaseRecords()
	if err != nil {
		return SDLPhaseAdmission{}, err
	}
	record, ok := records[digest.SHA256(request.Source)]
	if !ok || record.ContractID != request.ContractID || !record.SchemaAdmitted || !record.ModelAdmitted {
		return SDLPhaseAdmission{}, errors.New("native phase refused")
	}
	return SDLPhaseAdmission{ContractID: record.ContractID, SourceSHA256: record.SourceSHA256, Document: slices.Clone(record.Document)}, nil
}

func (c *materializationExecutionTestContext) AdmitSDLPhase(request SDLPhaseRequest) (SDLPhaseAdmission, error) {
	return (recordedSDLPhaseOwner{}).AdmitSDLPhase(request)
}

type alteredSDLPhaseOwner struct{ mode string }

func (o *alteredSDLPhaseOwner) AdmitSDLPhase(request SDLPhaseRequest) (SDLPhaseAdmission, error) {
	if o == nil || o.mode == "panic" {
		panic("private-native-owner")
	}
	if o.mode == "error" {
		return SDLPhaseAdmission{}, errors.New("private-native-owner")
	}
	phase, err := (recordedSDLPhaseOwner{}).AdmitSDLPhase(request)
	if err != nil {
		return phase, err
	}
	switch o.mode {
	case "contract":
		phase.ContractID = termRuntimeSnapshotV1
	case "digest":
		phase.SourceSHA256 = "sha256:" + strings.Repeat("0", 64)
	case "mutation":
		request.Source[0] = 'x'
	case "empty":
		phase.Document = nil
	case "shape":
		phase.Document = []byte(`[]`)
	case "duplicate":
		phase.Document = []byte(`{"name":"a","name":"b"}`)
	case "projection":
		phase.Document = []byte(`{"name":"unrelated"}`)
	}
	return phase, nil
}

func TestSDLPhaseAdmissionRequiresSourceBoundNativeOwner(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	raw := recordedNativeSource(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	for _, mode := range []string{"missing", "typed-nil", "panic", "error", "contract", "digest", "mutation", "empty", "shape", "duplicate", "projection"} {
		t.Run(mode, func(t *testing.T) {
			checkSDLPhaseRefusal(t, e, raw, limits, mode)
		})
	}
}

func recordedNativeSource(t *testing.T) []byte {
	t.Helper()
	var reference struct {
		Cases []localModelInputCase `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/local-model-inputs.json", &reference)
	for _, row := range reference.Cases {
		if row.Contract == termSdlAuthoringInputV1 && row.Admitted {
			return retainedModelInput(t, row)
		}
	}
	t.Fatal("no admitted native source reference")
	return nil
}

func checkSDLPhaseRefusal(t *testing.T, e *Validator, raw []byte, limits ingress.Limits, mode string) {
	t.Helper()
	var owner any = &alteredSDLPhaseOwner{mode: mode}
	if mode == "missing" {
		owner = nil
	}
	if mode == "typed-nil" {
		owner = (*alteredSDLPhaseOwner)(nil)
	}
	before := slices.Clone(raw)
	admitted, err := e.Validate(termSdlAuthoringInputV1, raw, limits, owner)
	if err == nil || admitted.ContractID() != "" || len(admitted.JSON()) != 0 || strings.Contains(err.Error(), "private-native-owner") {
		t.Fatalf("unsafe native owner admission: %v", err)
	}
	if !slices.Equal(before, raw) {
		t.Fatal("owner changed caller source bytes")
	}
	if _, err = e.Validate(termSdlAuthoringInputV1, raw, limits, recordedSDLPhaseOwner{}); err != nil {
		t.Fatalf("valid owner did not recover: %v", err)
	}
}
