package module

import (
	"bytes"
	"compress/gzip"
	"io"
	"os"
)

func readCompressedFixture(name string) ([]byte, error) {
	raw, err := os.ReadFile(name)
	if err != nil {
		return nil, err
	}
	reader, err := gzip.NewReader(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	defer func() { _ = reader.Close() }()
	return io.ReadAll(reader)
}
