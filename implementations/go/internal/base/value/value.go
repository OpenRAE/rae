// Package value admits bounded JSON snapshot values before copying or digesting.
// Unsupported carriers are rejected; no host type name becomes digest input.
package value

import (
	"encoding/json"
	"math"
	"math/big"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/internal/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
)

// The failure classes contain no rejected values.
var (
	ErrInput  = fault.New(fault.InvalidInput, "snapshot-value", nil)
	ErrLimits = fault.New(fault.InvalidInput, "value-limit-definition", nil)
	ErrLimit  = fault.New(fault.InvalidInput, "value-limit-exceeded", nil)
)

// MaterializationBytes is the authored document-body ceiling.
const MaterializationBytes = 4194304

// Limits are the shared finite-work limits, including budgets consumed by
// relation owners in addition to the value admission performed here.
type Limits struct {
	MaxDepth               int `json:"max_depth"`
	MaxNodes               int `json:"max_nodes"`
	MaxOperations          int `json:"max_operations"`
	MaxMembers             int `json:"max_members"`
	MaxIdentityChecks      int `json:"max_identity_checks"`
	MaxReferenceHops       int `json:"max_reference_hops"`
	MaxScalarBytes         int `json:"max_scalar_bytes"`
	MaxTotalScalarBytes    int `json:"max_total_scalar_bytes"`
	MaxDiagnostics         int `json:"max_diagnostics"`
	MaxDocumentScalarBytes int `json:"max_document_scalar_bytes,omitempty"`
}

// Default returns the default realization limits.
func Default() Limits {
	return Limits{
		MaxDepth: 32, MaxNodes: 4096, MaxOperations: 16384, MaxMembers: 4096,
		MaxIdentityChecks: 4096, MaxReferenceHops: 256, MaxScalarBytes: 4096,
		MaxTotalScalarBytes: 1048576, MaxDiagnostics: 16,
	}
}

// Runtime returns the portable runtime snapshot limits.
func Runtime() Limits {
	limits := Default()
	limits.MaxNodes, limits.MaxOperations, limits.MaxMembers = 65536, 4*65536, 16384
	limits.MaxScalarBytes, limits.MaxTotalScalarBytes = 1048576, 8*1048576
	limits.MaxDocumentScalarBytes = MaterializationBytes
	return limits
}

// Plan returns the larger node/operation budget for compiled authority plans.
func Plan() Limits {
	limits := Runtime()
	limits.MaxNodes, limits.MaxOperations = 262144, 4*262144
	return limits
}

// Validate checks all definition bounds before processing a value.
func (l Limits) Validate() error {
	for _, bound := range [][2]int{
		{l.MaxDepth, 1024}, {l.MaxNodes, 1000000}, {l.MaxOperations, 4000000},
		{l.MaxMembers, 100000}, {l.MaxIdentityChecks, 1000000},
		{l.MaxReferenceHops, 4096}, {l.MaxScalarBytes, 8 * 1048576},
		{l.MaxTotalScalarBytes, 64 * 1048576}, {l.MaxDiagnostics, 256},
	} {
		if bound[0] < 1 || bound[0] > bound[1] {
			return ErrLimits
		}
	}
	if l.MaxDocumentScalarBytes != 0 && (l.MaxDocumentScalarBytes < l.MaxScalarBytes ||
		l.MaxDocumentScalarBytes > l.MaxTotalScalarBytes || l.MaxDocumentScalarBytes > 8*1048576) {
		return ErrLimits
	}
	return nil
}

// DocumentText marks a field whose model explicitly grants the document-body
// ceiling. Wire strings cannot create this private representation themselves.
type DocumentText struct{ text string }

// DeclaredDocument is called by a model owner for a declared document field.
func DeclaredDocument(text string) DocumentText { return DocumentText{text: text} }

// MarshalJSON writes only the declared text, without a carrier marker.
func (d DocumentText) MarshalJSON() ([]byte, error) { return json.Marshal(d.text) }

type entry struct {
	value any
	depth int
}

type budget struct {
	limits Limits
	nodes  int
	bytes  int
}

// Validate admits exact JSON types and trusted declared document text.
// It never calls methods on an unknown carrier. The walk is iterative and
// bounded even for a cyclic Go map or slice.
func Validate(value any, limits Limits) error {
	if err := limits.Validate(); err != nil {
		return err
	}
	state := budget{limits: limits}
	pending := []entry{{value: value}}
	for len(pending) > 0 {
		item := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		state.nodes++
		if item.depth > limits.MaxDepth || state.nodes > limits.MaxNodes || state.nodes > limits.MaxOperations {
			return ErrLimit
		}
		children, err := state.visit(item)
		if err != nil {
			return err
		}
		if len(children) > limits.MaxNodes-state.nodes-len(pending) {
			return ErrLimit
		}
		pending = append(pending, children...)
	}
	return nil
}

func (b *budget) visit(item entry) ([]entry, error) {
	switch v := item.value.(type) {
	case map[string]any:
		if len(v) > b.limits.MaxMembers {
			return nil, ErrLimit
		}
		children := make([]entry, 0, len(v))
		for key, child := range v {
			if err := b.scalar(key, false); err != nil {
				return nil, err
			}
			children = append(children, entry{value: child, depth: item.depth + 1})
		}
		return children, nil
	case []any:
		if len(v) > b.limits.MaxMembers {
			return nil, ErrLimit
		}
		children := make([]entry, len(v))
		for i, child := range v {
			children[i] = entry{value: child, depth: item.depth + 1}
		}
		return children, nil
	case DocumentText:
		return nil, b.scalar(v.text, true)
	default:
		return nil, b.scalar(v, false)
	}
}

func (b *budget) scalar(value any, document bool) error {
	ceiling := b.limits.MaxScalarBytes
	if document && b.limits.MaxDocumentScalarBytes != 0 {
		ceiling = b.limits.MaxDocumentScalarBytes
	}
	size, err := scalarSize(value)
	if err != nil {
		return err
	}
	if size > ceiling || size > b.limits.MaxTotalScalarBytes-b.bytes {
		return ErrLimit
	}
	b.bytes += size
	return nil
}

func scalarSize(value any) (int, error) {
	switch v := value.(type) {
	case nil, bool:
		return 8, nil
	case string:
		if !utf8.ValidString(v) {
			return 0, ErrInput
		}
		return len(v), nil
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return 0, ErrInput
		}
		return 8, nil
	case int:
		return integerSize(big.NewInt(int64(v))), nil
	case int64:
		return integerSize(big.NewInt(v)), nil
	case *big.Int:
		if v != nil {
			return integerSize(v), nil
		}
	case json.Number:
		return numberSize(v)
	}
	return 0, ErrInput
}

func integerSize(value *big.Int) int { return max(1, (value.BitLen()+7)/8) }

func numberSize(number json.Number) (int, error) {
	text := string(number)
	if text == "" || !json.Valid([]byte(text)) || strings.TrimSpace(text) != text {
		return 0, ErrInput
	}
	if strings.ContainsAny(text, ".eE") {
		if _, err := strconv.ParseFloat(text, 64); err != nil {
			return 0, ErrInput
		}
		return 8, nil
	}
	if len(strings.TrimPrefix(text, "-")) > 4300 {
		return 0, ErrInput
	}
	integer, ok := new(big.Int).SetString(text, 10)
	if !ok {
		return 0, ErrInput
	}
	return integerSize(integer), nil
}

// Canonical admits a snapshot before invoking the canonical encoder. Unknown
// marshal callbacks are refused during validation, not invoked during encoding.
func Canonical(value any, limits Limits) ([]byte, error) {
	if err := Validate(value, limits); err != nil {
		return nil, err
	}
	snapshot, err := snapshot(value)
	if err != nil {
		return nil, err
	}
	text, err := json.Marshal(snapshot)
	if err != nil {
		return nil, err
	}
	return canonjson.JCS(text)
}

// snapshot preserves the int/float distinction that encoding/json's shortest
// float text can erase (for example float64(1e16) becomes integer text).
func snapshot(value any) (any, error) {
	switch v := value.(type) {
	case nil, bool, string, int, int64, json.Number:
		return v, nil
	case float64:
		return json.Number(strconv.FormatFloat(v, 'e', -1, 64)), nil
	case *big.Int:
		if v == nil {
			return nil, ErrInput
		}
		return json.Number(v.String()), nil
	case DocumentText:
		return v.text, nil
	case []any:
		items := make([]any, len(v))
		for i, item := range v {
			encoded, err := snapshot(item)
			if err != nil {
				return nil, err
			}
			items[i] = encoded
		}
		return items, nil
	case map[string]any:
		members := make(map[string]any, len(v))
		for key, item := range v {
			encoded, err := snapshot(item)
			if err != nil {
				return nil, err
			}
			members[key] = encoded
		}
		return members, nil
	default:
		return nil, ErrInput
	}
}
