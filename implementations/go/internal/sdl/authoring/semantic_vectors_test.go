package authoring

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

const (
	semanticFixtureFamily = "fixtures/sdl/semantic-vectors-v1"
	semanticShardBytes    = 450 * 1024
	semanticMaxShards     = 128
)

var errSemanticFixture = errors.New("invalid semantic fixture inventory or record")

type semanticManifest struct {
	Schema string          `json:"schema"`
	Count  int             `json:"case_count"`
	Shards []semanticShard `json:"shards"`
}

type semanticShard struct {
	Name   string `json:"name"`
	Count  int    `json:"case_count"`
	SHA256 string `json:"sha256"`
}

func readSemanticVectors(t *testing.T) []semanticVector {
	t.Helper()
	rows, err := loadSemanticVectors(os.DirFS("../../../../../contracts/" + semanticFixtureFamily))
	if err != nil {
		t.Fatal(err)
	}
	return rows
}

func loadSemanticVectors(source fs.FS) ([]semanticVector, error) {
	manifest, err := readSemanticManifest(source)
	if err != nil {
		return nil, err
	}
	var result []semanticVector
	seen := map[string]bool{}
	listed := map[string]bool{}
	for index, shard := range manifest.Shards {
		if shard.Name != fmt.Sprintf("semantics-%03d.json", index) || shard.Count < 1 {
			return nil, errSemanticFixture
		}
		listed[shard.Name] = true
		var rows []semanticVector
		rows, err = readSemanticShard(source, shard)
		if err != nil {
			return nil, fmt.Errorf("semantic shard %d: %w", index, err)
		}
		for _, row := range rows {
			if row.Name == "" || seen[row.Name] {
				return nil, errSemanticFixture
			}
			seen[row.Name] = true
		}
		result = append(result, rows...)
	}
	if len(result) != manifest.Count {
		return nil, errSemanticFixture
	}
	if err = checkSemanticShardInventory(source, listed); err != nil {
		return nil, err
	}
	return result, nil
}

func readSemanticManifest(source fs.FS) (semanticManifest, error) {
	raw, err := readSemanticFile(source, "semantics.json")
	var manifest semanticManifest
	if err != nil {
		return manifest, err
	}
	if _, err = decodeSemanticJSON(raw, ingress.Object, &manifest); err != nil || manifest.Schema != "raes-sdl-semantic-vectors/v1" || manifest.Count < 1 || len(manifest.Shards) < 1 || len(manifest.Shards) > semanticMaxShards {
		return manifest, errSemanticFixture
	}
	return manifest, nil
}

func checkSemanticShardInventory(source fs.FS, listed map[string]bool) error {
	entries, err := fs.ReadDir(source, ".")
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), "semantics-") && entry.Name() != "semantics-provenance.json" && !listed[entry.Name()] {
			return errSemanticFixture
		}
	}
	return nil
}

func readSemanticFile(source fs.FS, name string) ([]byte, error) {
	info, err := fs.Lstat(source, name)
	if err != nil || !info.Mode().IsRegular() {
		return nil, errSemanticFixture
	}
	file, err := source.Open(name)
	if err != nil {
		return nil, errSemanticFixture
	}
	data, readErr := io.ReadAll(io.LimitReader(file, semanticShardBytes+1))
	closeErr := file.Close()
	if readErr != nil || closeErr != nil || len(data) > semanticShardBytes {
		return nil, errSemanticFixture
	}
	return data, nil
}

func decodeSemanticJSON(data []byte, root ingress.Root, target any) (any, error) {
	value, err := ingress.Parse(data, ingress.Limits{MaxBytes: semanticShardBytes, MaxDepth: 64}, root)
	if err != nil {
		return nil, errSemanticFixture
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return nil, fmt.Errorf("semantic record type: %w", err)
	}
	return value, nil
}

func readSemanticShard(source fs.FS, shard semanticShard) ([]semanticVector, error) {
	data, err := readSemanticFile(source, shard.Name)
	if err != nil || digest.SHA256(data) != "sha256:"+shard.SHA256 {
		return nil, errSemanticFixture
	}
	var rows []semanticVector
	value, err := decodeSemanticJSON(data, ingress.Array, &rows)
	if err != nil {
		return nil, err
	}
	if len(rows) != shard.Count {
		return nil, errSemanticFixture
	}
	values, ok := value.([]any)
	if !ok {
		return nil, errSemanticFixture
	}
	for index, raw := range values {
		fields, ok := raw.(map[string]any)
		if !ok || !validSemanticRecord(rows[index], fields) {
			return nil, fmt.Errorf("semantic record %d: %w", index, errSemanticFixture)
		}
	}
	return rows, nil
}

func validSemanticRecord(row semanticVector, fields map[string]any) bool {
	if row.Name == "" || row.Source == "" || !nonNullSemanticValues(fields, "") || len(row.Findings) != len(row.Locations) {
		return false
	}
	if _, ok := fields["accepted"].(bool); !ok {
		return false
	}
	for _, name := range []string{"findings", "locations", "advisories"} {
		if _, ok := fields[name].([]any); !ok {
			return false
		}
	}
	if row.RecordExplicitness != (row.Explicitness != nil) {
		return false
	}
	return validSemanticResult(row)
}

func validSemanticResult(row semanticVector) bool {
	if row.Accepted {
		if len(row.Findings) != 0 || row.AdmissionError != "" {
			return false
		}
		if row.CanonicalError != "" {
			return row.CanonicalError == "SDLParseError" && row.Canonical == "" && row.Digest == ""
		}
		return row.Canonical != "" && row.Digest == digest.SHA256([]byte(row.Canonical))
	}
	if row.Canonical != "" || row.Digest != "" || row.CanonicalError != "" {
		return false
	}
	if row.AdmissionError != "" {
		return row.Materialized && row.AdmissionError == "materialized SDL exceeds portable bounds" && len(row.Findings) == 0 && len(row.Advisories) == 0
	}
	return len(row.Findings) != 0
}

// Only historical unowned findings and locations have null members.
func nonNullSemanticValues(value any, field string) bool {
	switch value := value.(type) {
	case map[string]any:
		return nonNullSemanticObject(value)
	case []any:
		for _, child := range value {
			if child == nil && field == "locations" {
				continue
			}
			if !nonNullSemanticValues(child, "") {
				return false
			}
		}
	}
	return value != nil
}

func nonNullSemanticObject(value map[string]any) bool {
	for key, child := range value {
		if child == nil && (key == "pointer" || key == "owner") {
			continue
		}
		if !nonNullSemanticValues(child, key) {
			return false
		}
	}
	return true
}
