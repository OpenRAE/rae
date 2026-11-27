package analysis

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

var sealedFixtureOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Read-only compiled registry shared by fixture readers.

// readTestFile reads a test file. A contract fixture gains its absent derived
// fields, as every fixture reader does for valid and context-invalid kinds.
func readTestFile(t *testing.T, path string) []byte {
	t.Helper()
	raw, err := os.ReadFile(path) //nolint:gosec // Paths come from repository-owned test tables and fixture identities.
	if err != nil {
		t.Fatal(err)
	}
	parts := strings.Split(filepath.ToSlash(path), "/")
	if !strings.Contains(filepath.ToSlash(path), "/contracts/fixtures/") || len(parts) < 3 {
		return raw
	}
	owner, err := sealedFixtureOwner()
	if err != nil {
		t.Fatal(err)
	}
	sealed, err := admission.SealFixture(owner, parts[len(parts)-3], parts[len(parts)-2], raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	return sealed
}
func testJSON(t *testing.T, value any) []byte {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
func testObject(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	value, err := decodeObject(raw, 16<<20)
	if err != nil {
		t.Fatal(err)
	}
	return value
}
func testAdmission(t *testing.T, id string, raw []byte, context any) validation.Value {
	t.Helper()
	owner, err := analysisOwner()
	if err != nil {
		t.Fatal(err)
	}
	value, err := owner.Validate(id, raw, ingress.Limits{MaxBytes: 16 << 20, MaxDepth: 128}, context)
	if err != nil {
		t.Fatal(err)
	}
	return value
}
func testGzip(t *testing.T, compressed []byte) []byte {
	t.Helper()
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := reader.Close(); closeErr != nil {
			t.Error(closeErr)
		}
	}()
	raw, err := io.ReadAll(io.LimitReader(reader, 16<<20+1))
	if err != nil || len(raw) > 16<<20 {
		t.Fatal("bounded fixture read", err)
	}
	return raw
}

type cliAnalysisFixture struct {
	Args   []string          `json:"args"`
	Files  map[string]string `json:"files"`
	Result struct {
		Stdout map[string]any `json:"stdout"`
	} `json:"result"`
}
