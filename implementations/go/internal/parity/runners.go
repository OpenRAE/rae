package parity

import (
	"context"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
)

// runners maps the key of each command that the Go implementation covers to
// its runner. Each Go port adds the commands that it implements.
func runners() map[string]Runner {
	return map[string]Runner{
		"canonical encode": canonicalEncode,
	}
}

// canonicalEncode returns the digest of each canonical form of a JSON value,
// or null for a form that refuses the value (issue #1779).
func canonicalEncode(_ context.Context, c Case) (json.RawMessage, error) {
	value := c.Files["value.json"]
	forms := map[string]func([]byte) ([]byte, error){
		"jcs":            canonjson.JCS,
		"sorted_ascii":   func(data []byte) ([]byte, error) { return canonjson.Sorted(data, true) },
		"sorted_unicode": func(data []byte) ([]byte, error) { return canonjson.Sorted(data, false) },
	}
	result := make(map[string]*string, len(forms))
	for form, encode := range forms {
		result[form] = nil
		if encoded, err := encode(value); err == nil {
			rendered := digest.SHA256(encoded)
			result[form] = &rendered
		}
	}
	return json.Marshal(result)
}
