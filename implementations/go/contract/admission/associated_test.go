package admission

import (
	"bytes"
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type associatedTestContext struct {
	parent   validation.Value
	payloads map[string]io.Reader
}

func (c associatedTestContext) AssociatedParent() validation.Value       { return c.parent }
func (c associatedTestContext) AssociatedParentDigest() string           { return "" }
func (c associatedTestContext) AssociatedPayloads() map[string]io.Reader { return c.payloads }

type failedArtifactReader struct{}

func (failedArtifactReader) Read([]byte) (int, error) { return 0, errors.New("private-reader-error") }

func TestAssociatedArtifactsBindDeclaredBytes(t *testing.T) {
	e := boundTestOwner(t)
	parent, err := e.low.Validate("sdl-authoring-input-v1", []byte(`{"name":"scenario","version":"1.0.0"}`), ingress.Limits{MaxBytes: 1024, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	v := decodeRuleObject(t, `{"schema_version":"associated-artifact-manifest/v1","manifest_id":"set","manifest_version":"1","canonicalization_profile":"associated-artifact-set/v1","scope":"scenario","parent_ref":{"ref_kind":"scenario","ref_id":"scenario"},"artifacts":{"file":{"artifact_id":"file","role":"other","media_type":"text/plain","uri":"urn:example:payload","checksum":{"algorithm":"sha256","value":"BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD"},"size_bytes":3,"created_at":"2026-01-01T00:00:00Z","source":"test","satisfies_refs":[],"sensitivity":"public"}},"set_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`)
	normal, err := e.defaulted("associated-artifact-manifest-v1", v)
	if err != nil {
		t.Fatal(err)
	}
	projection := map[string]any{"profile": at(normal, "canonicalization_profile"), "scope": at(normal, "scope"), "parent_ref": at(normal, "parent_ref"), "artifacts": at(normal, "artifacts")}
	associatedNormalize(projection)
	object(v)["set_digest"], err = jsonDigest(projection)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name    string
		readers map[string]io.Reader
		valid   bool
	}{
		{"exact", map[string]io.Reader{"file": strings.NewReader("abc")}, true},
		{"substitution", map[string]io.Reader{"file": strings.NewReader("abd")}, false},
		{"trailing", map[string]io.Reader{"file": strings.NewReader("abcd")}, false},
		{"short", map[string]io.Reader{"file": strings.NewReader("ab")}, false},
		{"missing", map[string]io.Reader{}, false},
		{"extra", map[string]io.Reader{"file": strings.NewReader("abc"), "other": strings.NewReader("")}, false},
		{"read-failure", map[string]io.Reader{"file": failedArtifactReader{}}, false},
		{"typed-nil", map[string]io.Reader{"file": (*bytes.Reader)(nil)}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := validateTestDocument(t, e, "associated-artifact-manifest-v1", v, associatedTestContext{parent, test.readers})
			if (err == nil) != test.valid {
				t.Errorf("validation=%v", err)
			}
			if err != nil && strings.Contains(err.Error(), "private-reader-error") {
				t.Error("reader error escaped")
			}
		})
	}
}

func TestAssociatedChecksumVectorsAndReadBound(t *testing.T) {
	// Independent published digest vectors for the UTF-8 bytes of "abc".
	for algorithm, value := range map[string]string{
		"sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
		"sha384": "cb00753f45a35e8bb5a03d699ac65007272c32ab0eded1631a8b605a43ff5bed8086072ba1e7cc2358baeca134c825a7",
		"sha512": "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
		"blake3": "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85",
	} {
		artifact := map[string]any{"checksum": map[string]any{"algorithm": algorithm, "value": value}}
		if err := associatedPayload(artifact, strings.NewReader("abc"), 3); err != nil {
			t.Errorf("%s: %v", algorithm, err)
		}
		reader := strings.NewReader("abc-private-trailing-data")
		if err := associatedPayload(artifact, reader, 3); err == nil {
			t.Errorf("%s accepted trailing bytes", algorithm)
		}
		if reader.Len() != len("private-trailing-data") {
			t.Error("read past declared size plus one")
		}
	}
}
