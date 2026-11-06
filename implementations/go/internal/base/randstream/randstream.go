// Package randstream implements the published random-stream profiles
// blake3-xof-v1 and blake3-xof-participant-v1 (Go port 06, issue #1779).
//
// A stream key derives from 32 bytes of root entropy through BLAKE3 key
// derivation, under a context that names the profile. A block is the keyed
// BLAKE3 output for the canonical bytes of a stream address, read from the
// offset of the address's local coordinate. The functions are pure: there is
// no cursor and no shared state, so a draw does not depend on the order of
// draws.
package randstream

import (
	"encoding/hex"
	"fmt"
	"io"
	"math"
	"math/big"

	"github.com/zeebo/blake3"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

const (
	// BlockBytes is the length of one raw block.
	BlockBytes = 32
	// KeyBytes is the length of root entropy and of a stream key.
	KeyBytes = 32
)

// ErrInput reports an unsupported profile or an invalid argument.
var ErrInput = fault.New(fault.InvalidInput, "random-stream", nil)

// Key is a stream key.
type Key [KeyBytes]byte

// Draw is the outcome of one bounded-integer draw. Attempts counts the
// rejected candidates. An exhausted draw has no value.
type Draw struct {
	Value     *big.Int
	Attempts  int
	Exhausted bool
}

// PublicSeed decodes an inline public seed: 64 hexadecimal digits in the
// hex-fixed-width encoding.
func PublicSeed(encoding, value string) ([]byte, error) {
	if encoding != "hex-fixed-width" {
		return nil, fmt.Errorf("%w: unsupported public seed encoding %q", ErrInput, encoding)
	}
	if len(value) != 2*KeyBytes {
		return nil, fmt.Errorf("%w: a public seed must contain exactly %d hexadecimal digits", ErrInput, 2*KeyBytes)
	}
	seed, err := hex.DecodeString(value)
	if err != nil {
		return nil, fmt.Errorf("%w: a public seed must decode to exactly %d bytes", ErrInput, KeyBytes)
	}
	return seed, nil
}

// DeriveKey derives the stream key of a profile from root entropy.
func DeriveKey(profile string, rootEntropy []byte) (Key, error) {
	if profile != "blake3-xof-v1" && profile != "blake3-xof-participant-v1" {
		return Key{}, fmt.Errorf("%w: unsupported random stream profile %q", ErrInput, profile)
	}
	if len(rootEntropy) != KeyBytes {
		return Key{}, fmt.Errorf("%w: root entropy must be exactly %d bytes", ErrInput, KeyBytes)
	}
	var key Key
	blake3.DeriveKey("raes-random-stream-v1|profile="+profile, rootEntropy, key[:])
	return key, nil
}

// Block returns length bytes of the keyed output for the canonical address
// bytes, from offset bytes after the start of the block of coordinate.
// Coordinate and offset are not negative.
func Block(key Key, address []byte, coordinate, offset int64, length int) ([]byte, error) {
	if length < 1 {
		return nil, fmt.Errorf("%w: a block length must be positive", ErrInput)
	}
	output, err := outputAt(key, address, coordinate, offset)
	if err != nil {
		return nil, err
	}
	block := make([]byte, length)
	_, _ = io.ReadFull(output, block) // The output is unbounded, so the read cannot fail.
	return block, nil
}

// outputAt makes a private reader for one operation. No cursor is shared
// between operations, and candidate reads need no multiplying attempt offset.
func outputAt(key Key, address []byte, coordinate, offset int64) (*blake3.Digest, error) {
	if coordinate < 0 || offset < 0 || coordinate > (math.MaxInt64-offset)/BlockBytes {
		return nil, fmt.Errorf("%w: the block position is out of range", ErrInput)
	}
	// NewKeyed fails only for a key of the wrong length, and Key has the right length.
	hasher, _ := blake3.NewKeyed(key[:])
	_, _ = hasher.Write(address) // A hash write cannot fail.
	output := hasher.Digest()
	if _, err := output.Seek(coordinate*BlockBytes+offset, io.SeekStart); err != nil {
		return nil, fmt.Errorf("%w: %w", ErrInput, err)
	}
	return output, nil
}

// BoundedInt draws an unbiased integer in [minimum, maximum] by rejection
// sampling. Each candidate is the smallest number of big-endian bytes that
// covers the range. A candidate at or above the largest multiple of the range
// width that fits those bytes is rejected, and the next candidate is read from
// the following bytes. After maxAttempts rejections the draw is exhausted; it
// never falls back to a biased value.
// Bounds and the returned value are exact integers; neither bound is changed.
func BoundedInt(key Key, address []byte, coordinate int64, minimum, maximum *big.Int, maxAttempts int) (Draw, error) {
	if minimum == nil || maximum == nil || maximum.Cmp(minimum) < 0 || maxAttempts < 1 {
		return Draw{}, fmt.Errorf("%w: a draw needs maximum >= minimum and at least one attempt", ErrInput)
	}
	output, err := outputAt(key, address, coordinate, 0)
	if err != nil {
		return Draw{}, err
	}
	width := new(big.Int).Sub(maximum, minimum)
	width.Add(width, big.NewInt(1))
	byteWidth := 1
	ceiling := big.NewInt(256)
	for ceiling.Cmp(width) < 0 {
		byteWidth++
		ceiling.Lsh(ceiling, 8)
	}
	limit := new(big.Int).Sub(ceiling, new(big.Int).Mod(ceiling, width))
	chunk := make([]byte, byteWidth)
	for attempt := range maxAttempts {
		_, _ = io.ReadFull(output, chunk) // The output always fills the buffer.
		candidate := new(big.Int).SetBytes(chunk)
		if candidate.Cmp(limit) < 0 {
			value := candidate.Mod(candidate, width)
			return Draw{Value: value.Add(value, minimum), Attempts: attempt}, nil
		}
	}
	return Draw{Attempts: maxAttempts, Exhausted: true}, nil
}
