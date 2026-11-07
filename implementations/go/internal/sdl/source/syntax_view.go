package source

// ParseSyntax checks YAML presentation and graph limits, retaining every pair
// and scalar spelling. It applies no scalar, mapping-key or model policy and
// grants no domain validity. Use Members, rather than Child, to inspect raw
// mappings whose duplicate and non-string keys have not yet been checked.
func ParseSyntax(data []byte, limits Limits, name string) (View, error) {
	options := DefaultOptions()
	options.Limits, options.Name, options.KeyScope = limits, name, dataScope
	if err := prepare(data, options); err != nil {
		return View{}, err
	}
	tokens, err := scan(data, options)
	if err != nil {
		return View{}, err
	}
	root, err := composeSyntax(tokens, data, options, true)
	if err != nil {
		return View{}, err
	}
	if err = measure(root, options); err != nil {
		return View{}, err
	}
	document := &Document{root: root, keyScope: dataScope}
	return document.View(), nil
}

// ViewMember retains one authored key/value pair as immutable cursors.
type ViewMember struct{ Key, Value View }

// Kind returns mapping, sequence or scalar; an absent cursor returns "".
func (v View) Kind() string {
	if v.current == nil {
		return ""
	}
	switch v.current.kind {
	case 'm':
		return "mapping"
	case 's':
		return "sequence"
	case 'v':
		return "scalar"
	}
	return ""
}

// Scalar returns decoded scalar text and its quoted status. A non-scalar
// returns empty text and false. No scalar resolver is called by this accessor.
func (v View) Scalar() (string, bool) {
	if v.current == nil || v.current.kind != 'v' {
		return "", false
	}
	return v.current.spelling, v.current.quoted
}

// Members copies the cursor pairs in the current mapping. Before domain
// policy, these include duplicate and merge keys. Non-mappings return nil.
func (v View) Members() []ViewMember {
	if v.current == nil || v.current.kind != 'm' {
		return nil
	}
	result := make([]ViewMember, len(v.current.entries))
	for i, entry := range v.current.entries {
		key, _ := entry.key.value.(string)
		scope := childScope(v.scope, canonical(key, v.scope), entry.value)
		result[i] = ViewMember{Key: View{document: v.document, current: entry.key, scope: v.scope}, Value: View{document: v.document, current: entry.value, scope: scope}}
	}
	return result
}

// Elements copies sequence cursors. Non-sequences return nil. Alias edges
// retain cursor identity, so graph consumers can memoize their own policy.
func (v View) Elements() []View {
	if v.current == nil || v.current.kind != 's' {
		return nil
	}
	result := make([]View, len(v.current.children))
	for i, child := range v.current.children {
		result[i] = View{document: v.document, current: child, scope: v.scope}
	}
	return result
}
