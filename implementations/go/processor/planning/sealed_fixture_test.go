package planning_test

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

var sealedFixtureOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Read-only compiled registry shared by fixture readers.

// readSealedFixture reads a repository contract fixture and fills its absent
// derived fields, as every fixture reader does for valid and context-invalid kinds.
func readSealedFixture(path string) ([]byte, error) {
	// The fixture reader is confined to the fixture directory.
	directory, name := filepath.Split(path)
	if directory == "" {
		directory = "."
	}
	raw, err := fs.ReadFile(os.DirFS(directory), name)
	if err != nil {
		return nil, err
	}
	owner, err := sealedFixtureOwner()
	if err != nil {
		return nil, err
	}
	parts := strings.Split(filepath.ToSlash(path), "/")
	return admission.SealFixture(owner, parts[len(parts)-3], parts[len(parts)-2], raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
}
