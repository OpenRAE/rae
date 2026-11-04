package admission

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

type materializationArchiveFixture struct {
	SDL          string          `json:"SDL"`
	SourceSHA256 string          `json:"SourceSHA256"`
	Document     json.RawMessage `json:"Document"`
	FullDocument json.RawMessage `json:"FullDocument"`
	Record       json.RawMessage `json:"Record"`
}

type materializationArchiveTestContext struct {
	source       []byte
	compilation  MaterializationCompilation
	fail, mutate bool
}

func (c *materializationArchiveTestContext) ArchivedMaterializationSDL() []byte { return c.source }
func (c *materializationArchiveTestContext) CompileMaterialization(request MaterializationCompileRequest) (MaterializationCompilation, error) {
	if c.fail || request.ContractID != "materialized-scenario-v1" || !bytes.Equal(request.Source, c.source) {
		return MaterializationCompilation{}, errors.New("private-compiler-refusal")
	}
	if c.mutate {
		request.Source[0] = 'x'
	}
	return c.compilation, nil
}
func (*materializationArchiveTestContext) NormalizeMaterializationNode(MaterializationNodeProjection) (json.RawMessage, error) {
	return nil, errors.New("unused-node-owner")
}

func materializationArchiveTestFixture(t *testing.T) ([]byte, *materializationArchiveTestContext) {
	t.Helper()
	// The incumbent protected archive and validate_materialization_archive_record
	// both admitted this synthetic source before its phase data was recorded.
	raw, err := os.ReadFile("testdata/materialization-archive.json")
	if err != nil {
		t.Fatal(err)
	}
	var g materializationArchiveFixture
	if err = json.Unmarshal(raw, &g); err != nil {
		t.Fatal(err)
	}
	return g.Record, &materializationArchiveTestContext{source: []byte(g.SDL), compilation: MaterializationCompilation{SourceSHA256: g.SourceSHA256, Document: g.Document, FullDocument: g.FullDocument}}
}

func TestMaterializationArchiveBindsProtectedBytesAndSemanticIdentity(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	raw, c := materializationArchiveTestFixture(t)
	if _, err := e.Validate("materialization-archive-record-v1", raw, limits, c); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"semantic-digest", "path", "size", "producer", "timestamp", "compiler-failure", "compiler-mutation", "source-commitment"} {
		t.Run(name, func(t *testing.T) {
			raw, c := materializationArchiveTestFixture(t)
			v, err := ingress.Parse(raw, limits, ingress.Object)
			if err != nil {
				t.Fatal(err)
			}
			materializationArchiveMutation(v, c, name)
			if _, err = e.Validate("materialization-archive-record-v1", controlJSON(t, v), limits, c); err == nil {
				t.Fatal("accepted substituted materialization archive")
			}
		})
	}
}

func materializationArchiveMutation(v any, c *materializationArchiveTestContext, name string) {
	switch name {
	case "semantic-digest":
		object(at(v, "reference"))["ref_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	case "path":
		object(at(v, "reference"))["ref_path"] = "runs/other/attestations/materialization-1.sdl"
	case "size":
		object(at(v, "artifact"))["size_bytes"] = jsonZero
	case "producer":
		object(at(v, "artifact"))["source"] = "another-producer"
	case "timestamp":
		object(at(v, "artifact"))["created_at"] = "2026-09-14T12:00:01+00:00"
	case "compiler-failure":
		c.fail = true
	case "compiler-mutation":
		c.mutate = true
	case "source-commitment":
		c.compilation.SourceSHA256 = "sha256:wrong"
	}
}
