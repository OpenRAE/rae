package module

import (
	"encoding/base64"
	"strings"
)

// The reference uses b64decode(validate=False). Discard ignored characters and
// stop at complete padding; the standard decoder still owns byte decoding.
func decodeSignatureBase64(raw string) ([]byte, error) {
	clean := make([]byte, 0, len(raw))
	padding := 0
	for _, char := range []byte(raw) {
		if signatureBase64Digit(char) {
			clean = append(clean, char)
			padding = 0
			continue
		}
		if char != '=' {
			continue
		}
		remainder := len(clean) % 4
		if remainder < 2 {
			continue
		}
		padding++
		if remainder+padding == 4 {
			return base64.StdEncoding.DecodeString(string(clean) + strings.Repeat("=", padding))
		}
	}
	return base64.StdEncoding.DecodeString(string(clean))
}
func signatureBase64Digit(char byte) bool {
	return char >= 'A' && char <= 'Z' || char >= 'a' && char <= 'z' || char >= '0' && char <= '9' || char == '+' || char == '/'
}
