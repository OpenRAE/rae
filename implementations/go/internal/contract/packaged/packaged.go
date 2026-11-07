// Package packaged reads documents of the embedded corpus for the packaged
// authority owners. Each document passes strict bounded ingress and, when it
// names a published contract, that schema.
package packaged

import (
	"errors"
	"io"
	"io/fs"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// MaxBytes and MaxDepth bound each packaged document.
const (
	MaxBytes = 8 << 20
	MaxDepth = 64
)

// ErrDocument reports a packaged document that is missing, too large, not
// strict JSON or not valid for its contract. Only a damaged build or
// installation can cause it.
var ErrDocument = errors.New("packaged document invalid")

// File names one packaged document. An empty ContractID skips the schema.
type File struct{ ContractID, Path string }

// Read returns the bytes of each file in order.
func Read(source fs.FS, schemas *validation.Validator, files []File) ([][]byte, error) {
	limits := ingress.Limits{MaxBytes: MaxBytes, MaxDepth: MaxDepth}
	result := make([][]byte, 0, len(files))
	for _, file := range files {
		data, err := readBounded(source, file.Path)
		if err != nil {
			return nil, err
		}
		if _, err := ingress.Parse(data, limits, ingress.Object); err != nil {
			return nil, ErrDocument
		}
		if file.ContractID != "" && schemas.CheckSchema(file.ContractID, data, limits) != nil {
			return nil, ErrDocument
		}
		result = append(result, data)
	}
	return result, nil
}

func readBounded(source fs.FS, path string) ([]byte, error) {
	file, err := source.Open(path)
	if err != nil {
		return nil, ErrDocument
	}
	data, readErr := io.ReadAll(io.LimitReader(file, MaxBytes+1))
	closeErr := file.Close()
	if readErr != nil || closeErr != nil || len(data) > MaxBytes {
		return nil, ErrDocument
	}
	return data, nil
}
