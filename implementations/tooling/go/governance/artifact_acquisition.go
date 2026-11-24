package governance

import (
	"context"
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

const genericArtifactLimit = 256 * 1024 * 1024

type artifactAcquisitionError string

func (e artifactAcquisitionError) Error() string          { return string(e) }
func (artifactAcquisitionError) Category() fault.Category { return fault.Operational }

func acquireLockedBytes(ctx context.Context, id, locator string, expected lockedRawObject, localInput string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	size, err := expected.size.Int64()
	if err != nil || size < 1 || size > genericArtifactLimit {
		return nil, artifactAcquisitionError(id + " locked raw size is outside the generic artifact budget")
	}
	if localInput != "" {
		bytes, readErr := readArtifactInput(localInput, size)
		if readErr != nil || !artifactMatches(bytes, expected, size) {
			return nil, artifactAcquisitionError(id + " local input failed locked identity validation")
		}
		return bytes, nil
	}
	temporary, err := artifactTemporaryDirectory()
	if err != nil {
		return nil, err
	}
	defer func() { _ = os.RemoveAll(temporary) }()
	output := filepath.Join(temporary, "raw-object")
	outcome, err := runArtifactCurl(ctx, locator, output, size)
	if err != nil {
		return nil, err
	}
	if outcome != "" {
		return nil, artifactAcquisitionError(id + " acquisition failed: " + outcome)
	}
	bytes, err := readArtifactInput(output, size)
	if err != nil {
		return nil, artifactAcquisitionError(id + " acquired output is unsafe")
	}
	if !artifactMatches(bytes, expected, size) {
		return nil, artifactAcquisitionError(id + " acquired bytes differ from the reviewed lock")
	}
	return bytes, nil
}

func readArtifactInput(name string, limit int64) ([]byte, error) {
	r, resolved, err := explicitFilePath(name, "artifact input")
	if err != nil {
		return nil, err
	}
	defer func() { _ = r.root.Close() }()
	before, err := r.root.Lstat(resolved)
	if err != nil {
		return nil, err
	}
	if !before.Mode().IsRegular() || before.Size() > limit {
		return nil, errArtifactSelection
	}
	return readSelectedFile(r, resolved, before, limit)
}
func artifactMatches(data []byte, expected lockedRawObject, size int64) bool {
	return int64(len(data)) == size && fmt.Sprintf("%x", sha256.Sum256(data)) == expected.digest
}
func artifactTemporaryDirectory() (string, error) {
	base, err := absoluteReferencePath(os.TempDir())
	if err != nil {
		return "", err
	}
	base, err = repositoryDirectory(base)
	if err != nil {
		return "", err
	}
	if strings.ContainsRune(base, 0) {
		return "", errUnsafePath
	}
	return os.MkdirTemp(base, "raes-artifact-acquisition-")
}
