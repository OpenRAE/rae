package parity

import (
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"path"
	"strconv"
)

const (
	pieceLimit = 256 * 1024
	blobLimit  = 64 * 1024 * 1024
	partsLimit = 512
)

// readLimited bounds allocation even when fsys contains an unexpectedly large file.
func readLimited(fsys fs.FS, name string, limit int64) ([]byte, error) {
	file, err := fsys.Open(name)
	if err != nil {
		return nil, err
	}
	content, readErr := io.ReadAll(io.LimitReader(file, limit+1))
	closeErr := file.Close()
	if err := errors.Join(readErr, closeErr); err != nil {
		return nil, err
	}
	if int64(len(content)) > limit {
		return nil, fmt.Errorf("%s exceeds the storage limit", name)
	}
	return content, nil
}

func readBlob(fsys fs.FS, identity string) ([]byte, error) {
	if !hexDigest(identity, 64) {
		return nil, errors.New("invalid parity blob identity")
	}
	encoded, err := readLimited(fsys, path.Join("inputs", identity), pieceLimit)
	if err != nil {
		return nil, err
	}
	if !bytes.HasPrefix(encoded, []byte{0x1f, 0x8b}) {
		encoded, err = readPieces(fsys, identity, encoded)
		if err != nil {
			return nil, err
		}
	}
	stream, err := gzip.NewReader(bytes.NewReader(encoded))
	if err != nil {
		return nil, err
	}
	content, readErr := io.ReadAll(io.LimitReader(stream, blobLimit+1))
	closeErr := stream.Close()
	if err := errors.Join(readErr, closeErr); err != nil {
		return nil, err
	}
	sum := sha256.Sum256(content)
	if len(content) > blobLimit || hex.EncodeToString(sum[:]) != identity {
		return nil, errors.New("parity input is oversized or does not match its digest")
	}
	return content, nil
}

func readPieces(fsys fs.FS, identity string, encoded []byte) ([]byte, error) {
	var index struct {
		Parts int `json:"parts"`
	}
	if err := decodeJSON(encoded, "piece index", &index); err != nil {
		return nil, err
	}
	if index.Parts <= 0 || index.Parts > partsLimit {
		return nil, errors.New("invalid parity input piece count")
	}
	var combined []byte
	for number := range index.Parts {
		piece, err := readLimited(fsys, path.Join("pieces", identity, strconv.Itoa(number)), pieceLimit+1)
		if err != nil {
			return nil, err
		}
		if len(piece) == 0 || piece[0] != 0 {
			return nil, errors.New("invalid parity input piece marker")
		}
		combined = append(combined, piece[1:]...)
	}
	return combined, nil
}

func documentBytes(fsys fs.FS, name string) ([]byte, error) {
	content, err := readLimited(fsys, name, pieceLimit)
	if err != nil {
		return nil, err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(content, &fields); err != nil {
		return nil, err
	}
	if reference, ok := fields["document_ref"]; ok && len(fields) == 1 {
		var identity string
		if err := json.Unmarshal(reference, &identity); err != nil {
			return nil, err
		}
		return readBlob(fsys, identity)
	}
	return content, nil
}
