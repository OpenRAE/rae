package module

import (
	"bytes"
	"io"
	"strconv"
	"strings"
)

// tarProfile preserves the publisher's fixed PAX byte profile while the
// standard tar writer owns record framing and payload padding. The input is
// locally generated records, never a received archive.
type tarProfile struct {
	output   io.Writer
	name     string
	block    [512]byte
	buffered int
	payload  int64
}

func (w *tarProfile) Write(raw []byte) (int, error) {
	total := 0
	for len(raw) > 0 {
		if w.payload > 0 {
			count := min(int64(len(raw)), w.payload)
			n, err := w.output.Write(raw[:count])
			w.payload -= int64(n)
			total += n
			raw = raw[n:]
			if err != nil {
				return total, err
			}
			if int64(n) != count {
				return total, io.ErrShortWrite
			}
			continue
		}
		count := copy(w.block[w.buffered:], raw)
		w.buffered += count
		total += count
		raw = raw[count:]
		if w.buffered != len(w.block) {
			continue
		}
		if err := w.header(); err != nil {
			return total, err
		}
		if _, err := w.output.Write(w.block[:]); err != nil {
			return total, err
		}
		w.buffered = 0
	}
	return total, nil
}
func (w *tarProfile) header() error {
	if bytes.Count(w.block[:], []byte{0}) == len(w.block) {
		return nil
	}
	size, err := strconv.ParseInt(string(bytes.Trim(w.block[124:136], "\x00 ")), 8, 64)
	if err != nil || size < 0 {
		return invalid()
	}
	w.payload = (size + 511) / 512 * 512
	clear(w.block[329:345]) // Device numbers are absent for regular and PAX records.
	name := w.name
	if w.block[156] == 'x' {
		name = "././@PaxHeader"
	}
	clear(w.block[:100])
	copy(w.block[:100], asciiName(name))
	for index := 148; index < 156; index++ {
		w.block[index] = ' '
	}
	var checksum int64
	for _, value := range w.block {
		checksum += int64(value)
	}
	encoded := strconv.FormatInt(checksum, 8)
	if len(encoded) > 6 {
		return invalid()
	}
	copy(w.block[148:154], strings.Repeat("0", 6-len(encoded))+encoded)
	w.block[154], w.block[155] = 0, ' '
	return nil
}
func asciiName(value string) string {
	return strings.Map(func(r rune) rune {
		if r > 127 {
			return '?'
		}
		return r
	}, value)
}
