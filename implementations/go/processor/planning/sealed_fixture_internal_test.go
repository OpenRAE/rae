package planning

import (
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

var sealedInternalFixtureOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Read-only compiled registry shared by fixture readers.

// readSealedInternalFixture reads a repository contract fixture and fills its absent
// derived fields, as every fixture reader does for valid and context-invalid kinds.
func readSealedInternalFixture(path string) ([]byte, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	owner, err := sealedInternalFixtureOwner()
	if err != nil {
		return nil, err
	}
	parts := strings.Split(filepath.ToSlash(path), "/")
	return admission.SealFixture(owner, parts[len(parts)-3], parts[len(parts)-2], raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
}
