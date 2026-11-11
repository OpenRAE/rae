package module

import (
	"bytes"
	"compress/gzip"
	"errors"
	"io"
)

// gzipSequence keeps the standard checksum and header validation while accepting
// zero padding between members, as the reference's gzip.GzipFile does.
type gzipSequence struct {
	input   *bytes.Reader
	current *gzip.Reader
}

func openGzipSequence(raw []byte) (*gzipSequence, error) {
	input := bytes.NewReader(raw)
	current, err := gzip.NewReader(input)
	if err != nil {
		return nil, err
	}
	current.Multistream(false)
	return &gzipSequence{input: input, current: current}, nil
}
func (g *gzipSequence) Read(target []byte) (int, error) {
	if len(target) == 0 {
		return 0, nil
	}
	for {
		count, err := g.current.Read(target)
		if !errors.Is(err, io.EOF) {
			return count, err
		}
		if count > 0 {
			return count, nil
		}
		if err = g.next(); err != nil {
			return 0, err
		}
	}
}
func (g *gzipSequence) next() error {
	for {
		char, err := g.input.ReadByte()
		if err != nil {
			return err
		}
		if char == 0 {
			continue
		}
		if err = g.input.UnreadByte(); err != nil {
			return err
		}
		if err = g.current.Reset(g.input); err != nil {
			return err
		}
		g.current.Multistream(false)
		return nil
	}
}
func (g *gzipSequence) Close() error { return g.current.Close() }
