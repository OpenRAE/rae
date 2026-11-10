package module

import "testing"

func TestSignatureBase64MatchesReference(t *testing.T) {
	for _, row := range []struct {
		encoded, decoded string
		valid            bool
	}{
		{"QUJD", "ABC", true}, {"====QUJD", "ABC", true}, {"QUJD====", "ABC", true},
		{"Q=U=J=D=", "AB", true}, {"QU=JD", "ABC", true}, {"QU==JD", "A", true},
		{"QUJ=Djunk", "AB", true}, {"QU=J=D", "AB", true}, {"QU=!=", "A", true},
		{"Q===", "", false}, {"QU", "", false}, {"QUJ", "", false},
		{"Q U\tJ\r\nD🙂", "ABC", true},
	} {
		t.Run(row.encoded, func(t *testing.T) {
			decoded, err := decodeSignatureBase64(row.encoded)
			if (err == nil) != row.valid || row.valid && string(decoded) != row.decoded {
				t.Fatalf("decoded=%q, %v; want %q, valid=%v", decoded, err, row.decoded, row.valid)
			}
		})
	}
}
