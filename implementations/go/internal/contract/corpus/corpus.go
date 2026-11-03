// Package corpus exposes the normative corpus embedded in Go binaries.
// Files are read-only. Runtime access never consults a checkout or the network.
package corpus

import (
	"archive/zip"
	"bytes"
	"embed"
	"encoding/hex"
	"errors"
	"io/fs"
)

// The embed directive requires a package variable. embed.FS has no write API.
//
//go:embed data/*
var pieces embed.FS

// Open returns the packaged corpus. Corrupt or missing resources are errors.
func Open() (fs.FS, error) { return openPieces(pieces) }

func openPieces(source fs.FS) (fs.FS, error) {
	entries, err := fs.ReadDir(source, "data")
	if err != nil || len(entries) > 64 {
		return nil, errors.New("corpus: missing or excessive embedded resources")
	}
	var data bytes.Buffer
	for _, entry := range entries {
		piece, readErr := fs.ReadFile(source, "data/"+entry.Name())
		if readErr != nil {
			return nil, errors.New("corpus: missing embedded piece")
		}
		piece = bytes.TrimSuffix(piece, []byte("\n"))
		if len(piece) > 262144 {
			return nil, errors.New("corpus: oversized embedded piece")
		}
		decoded := make([]byte, hex.DecodedLen(len(piece)))
		count, decodeErr := hex.Decode(decoded, piece)
		if decodeErr != nil {
			return nil, errors.New("corpus: invalid embedded encoding")
		}
		_, _ = data.Write(decoded[:count])
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
