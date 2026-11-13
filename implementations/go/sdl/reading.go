package sdl

import (
	"errors"
	"io"
	"io/fs"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// Read the ceiling and then probe one byte. Adding one to a trusted ceiling
// could overflow int64 and turn a permitted read into an empty document.
func readSource(file fs.File, limit int64) ([]byte, error) {
	raw, err := io.ReadAll(io.LimitReader(file, limit))
	count := 0
	if err == nil {
		var extra [1]byte
		count, err = io.ReadFull(file, extra[:])
		if errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF) {
			err = nil
		}
	}
	closeErr := file.Close()
	if err != nil || closeErr != nil {
		return nil, fault.New(fault.Operational, "sdl-source-read", nil)
	}
	if count != 0 {
		return nil, invalidScenario()
	}
	return raw, nil
}
