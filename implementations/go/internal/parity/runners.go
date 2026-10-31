package parity

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/internal/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/randstream"
)

// runners maps the key of each command that the Go implementation covers to
// its runner. Each Go port adds the commands that it implements.
func runners() map[string]Runner {
	return map[string]Runner{
		"canonical encode":  canonicalEncode,
		"randstream vector": randstreamVector,
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

// randstreamVector derives the stream key, the canonical address bytes, the
// raw block, and the bounded draw of a published random-stream vector
// (issue #1779).
func randstreamVector(_ context.Context, c Case) (json.RawMessage, error) {
	var vector struct {
		Profile string `json:"profile_id"`
		Seed    struct {
			Encoding string `json:"encoding"`
			Value    string `json:"value"`
		} `json:"root_entropy"`
		Address   json.RawMessage `json:"address"`
		Transform *struct {
			Minimum     int64 `json:"minimum"`
			Maximum     int64 `json:"maximum"`
			MaxAttempts int   `json:"max_rejection_attempts"`
		} `json:"transform"`
	}
	if err := json.Unmarshal(c.Files["vector.json"], &vector); err != nil {
		return nil, err
	}
	var position struct {
		Coordinate int64 `json:"local_coordinate"`
	}
	if err := json.Unmarshal(vector.Address, &position); err != nil {
		return nil, err
	}
	seed, err := randstream.PublicSeed(vector.Seed.Encoding, vector.Seed.Value)
	if err != nil {
		return nil, err
	}
	key, err := randstream.DeriveKey(vector.Profile, seed)
	if err != nil {
		return nil, err
	}
	address, err := canonjson.JCS(vector.Address)
	if err != nil {
		return nil, err
	}
	block, err := randstream.Block(key, address, position.Coordinate, 0, randstream.BlockBytes)
	if err != nil {
		return nil, err
	}
	result := map[string]any{
		"stream_key_hex":              hex.EncodeToString(key[:]),
		"address_canonical_bytes_hex": hex.EncodeToString(address),
		"raw_block_hex":               hex.EncodeToString(block),
	}
	if vector.Transform != nil {
		t := vector.Transform
		draw, err := randstream.BoundedInt(key, address, position.Coordinate, t.Minimum, t.Maximum, t.MaxAttempts)
		if err != nil {
			return nil, err
		}
		var value *string
		if !draw.Exhausted {
			text := strconv.FormatInt(draw.Value, 10)
			value = &text
		}
		result["draw"] = map[string]any{"value": value, "rejection_attempts": draw.Attempts, "rejection_exhausted": draw.Exhausted}
	}
	return json.Marshal(result)
}
