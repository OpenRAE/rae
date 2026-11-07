package source

import (
	"encoding/json"
	"strings"
)

// Budget shares aggregate accounting across one composition request.
// A composition owner must charge each import before reading its source and
// each document before combining or copying it. A Budget is request-local.
type Budget struct {
	limits         Limits
	imports, nodes int
	bytes          int64
}

// NewBudget validates limits before starting aggregate accounting.
func NewBudget(limits Limits) (*Budget, error) {
	if err := limits.Validate(); err != nil {
		return nil, err
	}
	return &Budget{limits: limits}, nil
}

// AddImport reserves one import edge before its read or resolution work.
func (b *Budget) AddImport() error {
	if b.imports >= b.limits.MaxImports {
		return importFailure("budget-exceeded")
	}
	b.imports++
	return nil
}

// AddBytes reserves raw lock bytes or other composition-owned decoded bytes.
func (b *Budget) AddBytes(count int64) error {
	if count < 0 || count > b.limits.MaxComposedBytes-b.bytes {
		return importFailure("budget-exceeded")
	}
	b.bytes += count
	return nil
}

// CheckDepth refuses an import before descending beyond the request depth.
func (b *Budget) CheckDepth(depth int) error {
	if depth < 0 || depth > b.limits.MaxCompositionDepth {
		return importFailure("budget-exceeded")
	}
	return nil
}

// AddDocument charges the expanded, merged document without copying its value.
// Failed reservations leave the request unusable; callers return the refusal.
func (b *Budget) AddDocument(d *Document) error {
	pending := []*node{d.root}
	for len(pending) > 0 {
		n := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if b.nodes >= b.limits.MaxComposedNodes {
			return importFailure("budget-exceeded")
		}
		b.nodes++
		if text, ok := n.value.(string); ok {
			if err := b.AddBytes(int64(len(text))); err != nil {
				return err
			}
		}
		pending = append(pending, children(n)...)
	}
	return nil
}

// CheckNamespace checks a generated qualified identity before namespace composition.
func (b *Budget) CheckNamespace(name string) error {
	if !qualified(name) {
		return importFailure("namespace-invalid")
	}
	parts := strings.Split(name, ".")
	if len(parts)-1 > b.limits.MaxNamespaceDepth {
		return importFailure("budget-exceeded")
	}
	return nil
}

// AddValue charges normalized source JSON before model coercion and serializer
// omissions. It does not copy or admit the value. Native carriers outside the
// JSON domain are refused, and repeated references are charged on every visit.
func (b *Budget) AddValue(value any) error {
	pending := []any{value}
	for len(pending) > 0 {
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if b.nodes >= b.limits.MaxComposedNodes {
			return importFailure("budget-exceeded")
		}
		b.nodes++
		if err := b.queueValue(current, &pending); err != nil {
			return err
		}
	}
	return nil
}
func (b *Budget) queueValue(value any, pending *[]any) error {
	remaining := b.limits.MaxComposedNodes - b.nodes - len(*pending)
	switch v := value.(type) {
	case string:
		return b.AddBytes(int64(len(v)))
	case map[string]any:
		if len(v) > remaining/2 {
			return importFailure("budget-exceeded")
		}
		for name, child := range v {
			*pending = append(*pending, name, child)
		}
	case []any:
		if len(v) > remaining {
			return importFailure("budget-exceeded")
		}
		*pending = append(*pending, v...)
	case nil, bool, json.Number, float64:
		// Scalar validation belongs to the source/model owner, not accounting.
	default:
		return importFailure("source-refused")
	}
	return nil
}
