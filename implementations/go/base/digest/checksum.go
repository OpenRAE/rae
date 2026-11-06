package digest

import (
	"crypto/sha256"
	"crypto/sha512"
	"hash"

	"github.com/zeebo/blake3"
)

// NewChecksum constructs an incremental checksum for a published algorithm.
// Unknown names return nil and false. The caller owns byte and reader bounds.
func NewChecksum(algorithm string) (hash.Hash, bool) {
	switch algorithm {
	case "sha256":
		return sha256.New(), true
	case "sha384":
		return sha512.New384(), true
	case "sha512":
		return sha512.New(), true
	case "blake3":
		return blake3.New(), true
	default:
		return nil, false
	}
}
