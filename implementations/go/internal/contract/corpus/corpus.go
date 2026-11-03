// Package corpus exposes the normative corpus embedded in Go binaries.
// Files are read-only. Runtime access never consults a checkout or the network.
package corpus

import (
	"archive/zip"
	"bytes"
	"embed"
	"errors"
	"io/fs"
)

// The embed directive requires a package variable. embed.FS has no write API.
//
//go:embed data/*
var pieces embed.FS

// Open returns the packaged corpus. Corrupt or missing resources are errors.
func Open() (fs.FS, error) {
	entries, err := pieces.ReadDir("data")
	if err != nil {
		return nil, errors.New("corpus: missing embedded resources")
	}
	var data bytes.Buffer
	for _, entry := range entries {
		piece, readErr := pieces.ReadFile("data/" + entry.Name())
		if readErr != nil {
			return nil, errors.New("corpus: missing embedded piece")
		}
		_, _ = data.Write(piece)
	}
	return openArchive(data.Bytes())
}

func openArchive(data []byte) (fs.FS, error) {
	reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, errors.New("corpus: invalid embedded archive")
	}
	if len(reader.File) == 0 {
		return nil, errors.New("corpus: empty embedded archive")
	}
	seen := map[string]bool{}
	for _, file := range reader.File {
		if !fs.ValidPath(file.Name) || seen[file.Name] || file.Mode()&fs.ModeSymlink != 0 {
			return nil, errors.New("corpus: invalid embedded member")
		}
		seen[file.Name] = true
	}
	return reader, nil
}
