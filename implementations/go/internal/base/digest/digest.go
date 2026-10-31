// Package digest renders the SHA-256 digests that RAES records and evidence
// contain (Go port 06, issue #1779). A rendering never changes, because
// persisted records hold it.
package digest

import (
	"crypto/sha256"
	"encoding/hex"
)

// Prefix is the algorithm label of a rendered digest.
const Prefix = "sha256:"

// SHA256 returns the rendered SHA-256 digest of data: the prefix and 64
// lowercase hexadecimal digits.
func SHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return Prefix + hex.EncodeToString(sum[:])
}
