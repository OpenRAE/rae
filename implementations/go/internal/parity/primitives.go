package parity

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
)

const (
	valueField  = "value"
	validField  = "valid"
	codeField   = "code"
	statusField = "status"
	invalidCode = "invalid"
)

// primitive runs the input-boundary API against a Python-recorded request.
func primitive(_ context.Context, c Case) (json.RawMessage, error) {
	var request primitiveRequest
	if err := json.Unmarshal(c.Files["request.json"], &request); err != nil {
		return nil, err
	}
	var result map[string]any
	switch c.Command {
	case "ingress", "ingress-exception":
		return primitiveIngress(request)
	case "uri":
		return primitiveURI(request)
	case "pointer":
		var index *int
		if i, ok := jsonpointer.ArrayIndex(request.Token, request.Length); ok {
			index = &i
		}
		result = map[string]any{"escape": jsonpointer.EscapeToken(request.Token), "unescape": jsonpointer.UnescapeToken(request.Token),
			"is_index": jsonpointer.IsArrayIndex(request.Token), "index": index}
	case "tokens":
		tokens := jsonpointer.Tokens(request.Pointer)
		result = map[string]any{"tokens": tokens, "pointer": jsonpointer.FromTokens(tokens)}
	case "address":
		result = map[string]any{validField: address.Valid(request.Value), "temporal": address.CompilerOwnedTemporalSubject(request.Value)}
	case "render":
		var value *string
		if rendered, err := address.Render(request.Parts...); err == nil {
			value = &rendered
		}
		result = map[string]any{valueField: value}
	case "plan-root":
		var value *string
		if root, ok := address.PlanRoot(request.Domain); ok {
			value = &root
		}
		result = map[string]any{valueField: value}
	default:
		return nil, fmt.Errorf("unknown primitive command: %s", c.Command)
	}
	return json.Marshal(result)
}

type primitiveRequest struct {
	Hex      string   `json:"hex"`
	Root     string   `json:"root"`
	MaxBytes int      `json:"max_bytes"`
	MaxDepth int      `json:"max_depth"`
	URI      string   `json:"uri"`
	Strict   bool     `json:"strict"`
	Token    string   `json:"token"`
	Length   int      `json:"length"`
	Pointer  string   `json:"pointer"`
	Value    string   `json:"value"`
	Parts    []string `json:"parts"`
	Domain   string   `json:"domain"`
}

func primitiveIngress(request primitiveRequest) (json.RawMessage, error) {
	data, err := hex.DecodeString(request.Hex)
	if err != nil {
		return nil, err
	}
	root := ingress.Array
	if request.Root == "object" {
		root = ingress.Object
	}
	value, err := ingress.Parse(data, ingress.Limits{MaxBytes: request.MaxBytes, MaxDepth: request.MaxDepth}, root)
	if failure, ok := errors.AsType[*ingress.Error](err); ok {
		return json.Marshal(map[string]any{codeField: failure.Code})
	}
	if err != nil {
		return nil, err
	}
	text, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	sorted, err := canonjson.Sorted(text, true)
	if err != nil {
		return nil, err
	}
	return json.Marshal(map[string]any{"sorted": string(sorted)})
}

func primitiveURI(request primitiveRequest) (json.RawMessage, error) {
	opts := urisafety.Options{}
	if request.Strict {
		opts = urisafety.Options{ForbiddenSchemes: []string{"data", "FTP"}, ForbidFragment: true}
	}
	err := urisafety.Check(request.URI, opts)
	code := ""
	for _, refusal := range []struct {
		err  error
		code string
	}{
		{urisafety.ErrInvalid, invalidCode}, {urisafety.ErrNotAbsolute, "absolute"},
		{urisafety.ErrForbiddenScheme, "scheme"}, {urisafety.ErrCredentials, "credentials"},
		{urisafety.ErrFragment, "fragment"}, {urisafety.ErrSecretQuery, "secret"},
	} {
		if errors.Is(err, refusal.err) {
			code = refusal.code
			break
		}
	}
	if err != nil && code == "" {
		return nil, err
	}
	return json.Marshal(map[string]any{codeField: code})
}
