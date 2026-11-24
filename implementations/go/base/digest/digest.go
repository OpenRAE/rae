// Package digest renders the SHA-256 digests that RAES records and evidence
// contain (Go port 06, issue #1779). A rendering never changes, because
// persisted records hold it.
package digest

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// Prefix is the algorithm label of a rendered digest.
const Prefix = "sha256:"

// SHA256 returns the rendered SHA-256 digest of data: the prefix and 64
// lowercase hexadecimal digits.
func SHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return Prefix + hex.EncodeToString(sum[:])
}

// Valid reports the published digest-string grammar, including uppercase hex.
// Rendering SHA256 remains the canonical lowercase form.
func Valid(text string) bool {
	algorithm, value, found := strings.Cut(text, ":")
	if !found {
		return false
	}
	var size int
	switch algorithm {
	case "sha256", "blake3":
		size = 64
	case "sha384":
		size = 96
	case "sha512":
		size = 128
	default:
		return false
	}
	if len(value) != size {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}
