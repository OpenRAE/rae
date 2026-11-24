package governance

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
)

func publicationJSON(value any) ([]byte, error) {
	var out bytes.Buffer
	if err := writePublicationJSON(&out, value); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func publicationDigest(value any) (string, error) {
	data, err := publicationJSON(value)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", sha256.Sum256(data)), nil
}

// Containers use the reference's sorted Unicode keys and compact separators.
// Scalar canonicalization remains with the existing public owner; this layer
// adds only the legacy allow_nan spellings that owner's finite profile refuses.
func writePublicationJSON(out *bytes.Buffer, value any) error {
	switch v := value.(type) {
	case *mapping:
		return writePublicationObject(out, v)
	case []any:
		return writePublicationArray(out, v)
	default:
		data, err := publicationScalar(value)
		if err != nil {
			return err
		}
		_, _ = out.Write(data)
		return nil
	}
}

func writePublicationObject(out *bytes.Buffer, value *mapping) error {
	out.WriteByte('{')
	for i, key := range sortedMappingKeys(value) {
		if i > 0 {
			out.WriteByte(',')
		}
		data, err := publicationScalar(key)
		if err != nil {
			return err
		}
		_, _ = out.Write(data)
		out.WriteByte(':')
		if err := writePublicationJSON(out, value.get(key)); err != nil {
			return err
		}
	}
	out.WriteByte('}')
	return nil
}

func writePublicationArray(out *bytes.Buffer, value []any) error {
	out.WriteByte('[')
	for i, item := range value {
		if i > 0 {
			out.WriteByte(',')
		}
		if err := writePublicationJSON(out, item); err != nil {
			return err
		}
	}
	out.WriteByte(']')
	return nil
}

func publicationScalar(value any) ([]byte, error) {
	if text, ok := value.(string); ok && !utf8.ValidString(text) {
		return nil, policyInputError("published schema text has no UTF-8 form")
	}
	if number, ok := value.(float64); ok {
		switch {
		case math.IsNaN(number):
			return []byte("NaN"), nil
		case math.IsInf(number, 1):
			return []byte("Infinity"), nil
		case math.IsInf(number, -1):
			return []byte("-Infinity"), nil
		default:
			// Exponent notation retains the float category even for 1.0 and
			// signed zero; Sorted owns the final Python-compatible spelling.
			return canonjson.Sorted([]byte(strconv.FormatFloat(number, 'e', -1, 64)), false)
		}
	}
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	return canonjson.Sorted(data, false)
}
