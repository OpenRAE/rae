package source

import "github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"

// View is an immutable cursor over a checked source graph. Its zero value is
// absent. Child follows a canonical mapping key or an RFC 6901 array index.
type View struct {
	document *Document
	current  *node
	scope    string
}

// View returns a cursor at the document root without copying its values.
func (d *Document) View() View { return View{document: d, current: d.root, scope: d.keyScope} }

// Keys copies canonical keys in construction order, including merged keys.
// It returns nil for an absent or non-mapping cursor.
func (v View) Keys() []string {
	if v.current == nil || v.current.kind != 'm' {
		return nil
	}
	result := make([]string, 0, len(v.current.entries))
	for _, entry := range v.current.entries {
		key, _ := entry.key.value.(string)
		result = append(result, canonical(key, v.scope))
	}
	return result
}

// Child returns an absent cursor when the token does not identify a child.
func (v View) Child(token string) View {
	if v.current == nil {
		return View{}
	}
	if v.current.kind == 's' {
		index, ok := jsonpointer.ArrayIndex(token, len(v.current.children))
		if !ok {
			return View{}
		}
		return View{document: v.document, current: v.current.children[index], scope: v.scope}
	}
	if v.current.kind != 'm' {
		return View{}
	}
	index := v.document.memberIndex(v.current, v.scope)
	child, ok := index[token]
	if !ok {
		return View{}
	}
	return View{document: v.document, current: child, scope: childScope(v.scope, token, child)}
}

// Range copies the original value range at this cursor, including alias
// declaration locations and the reference's inherited mapping locations.
func (v View) Range() (Range, bool) {
	if v.current == nil {
		return Range{}, false
	}
	return v.current.location(), true
}

func (d *Document) memberIndex(n *node, scope string) map[string]*node {
	key := walkKey{n, scope}
	if cached, ok := d.index.Load(key); ok {
		index, _ := cached.(map[string]*node)
		return index
	}
	index := make(map[string]*node, len(n.entries))
	for _, entry := range n.entries {
		name, _ := entry.key.value.(string)
		index[canonical(name, scope)] = entry.value
	}
	cached, _ := d.index.LoadOrStore(key, index)
	result, _ := cached.(map[string]*node)
	return result
}
func (n *node) location() Range {
	if n.locationSpan.Start.Line > 0 {
		return n.locationSpan
	}
	return n.span
}

func (d *Document) rangeMetadata() *Document {
	result := &Document{ranges: map[string]Range{}, keyRanges: map[string]Range{}}
	result.collectRanges(d.root, d.keyScope, d.baseTokens)
	return result
}
