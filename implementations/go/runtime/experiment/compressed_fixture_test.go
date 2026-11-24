package experiment

import (
	"compress/gzip"
	"errors"
	"io"
	"os"
)

func readCompressedReference(path string) ([]byte, error) {
	file, err := os.Open(path) //nolint:gosec // Every caller uses a literal repository fixture path.
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	reader, err := gzip.NewReader(file)
	if err != nil {
		return nil, err
	}
	defer func() { _ = reader.Close() }()
	data, err := io.ReadAll(io.LimitReader(reader, (32<<20)+1))
	if err != nil {
		return nil, err
	}
	if len(data) > 32<<20 {
		return nil, errors.New("reference fixture exceeds the byte limit")
	}
	return data, nil
}
