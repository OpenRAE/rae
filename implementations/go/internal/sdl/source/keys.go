package source

import (
	"errors"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	"golang.org/x/text/cases"
	"golang.org/x/text/language"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const (
	structuralScope   = "structural"
	literalScope      = "literal"
	dataScope         = "data"
	nodesSection      = "nodes"
	forwardingSection = "forwarding_agents"
	entitiesSection   = "entities"
	nullText          = "null"
	trueText          = "true"
	falseText         = "false"
)

func canonical(key, scope string) string {
	if scope == structuralScope {
		lower := strings.ToLower(key)
		if !asciiText(key) {
			lower = cases.Lower(language.Und).String(key)
		}
		return strings.ReplaceAll(lower, "-", "_")
	}
	return key
}
func inWords(word, words string) bool { return strings.Contains(" "+words+" ", " "+word+" ") }

const declarations = "nodes infrastructure features conditions propositions assertions entities injects events scripts stories content control_context_assets generated_artifacts persistent_volumes accounts identity_domains identity_forests identity_facades deployment_tenants deployment_cells relationships agents action_contracts observation_boundaries outcome_interpretation_rules behavior_specifications evidence_requirements time_domains clocks time_domain_mappings time_progression_policies temporal_constraints objectives workflows variables variation_points"
const literalFields = "features conditions injects roles log_options labels driver_options ipam_options facts entities events steps extensions interactive_access control_context controller_states transitions permitted_transitions alternatives inventory members fixed_positions tool_affordances participant_inject_deliveries owners dimensions"

func childScope(scope, key string, value *node) string {
	if scope == dataScope || scope == structuralScope && (key == "schema_document" || key == "profile_value") {
		return dataScope
	}
	if scope == structuralScope && ((inWords(key, declarations) || key == "vulnerabilities") && value.kind == 'm' || inWords(key, literalFields) || key == "properties" && value.kind == 's') {
		return literalScope
	}
	return structuralScope
}
func pointerTokens(s string) ([]string, error) {
	if s == "" {
		return nil, nil
	}
	if !strings.HasPrefix(s, "/") {
		return nil, errors.New("base pointer must be an RFC 6901 pointer")
	}
	return jsonpointer.Tokens(s), nil
}
func descend(tokens []string, key string) []string { return append(slices.Clone(tokens), key) }
func authored(n *node) string {
	if n.kind != 'v' {
		return "?"
	}
	return n.spelling
}

type walkKey struct {
	node  *node
	scope string
}
type effective struct {
	entries   []member
	conflicts [][2]member
}
type keyAnalysis struct {
	options      Options
	document     *Document
	items        []Diagnostic
	seen         map[string]bool
	walked       map[walkKey]bool
	cache        map[walkKey]effective
	materialized bool
}

func analyze(d *Document, options Options) error {
	tokens, err := pointerTokens(options.BasePointer)
	if err != nil {
		return err
	}
	a := keyAnalysis{options: options, document: d, seen: map[string]bool{}, walked: map[walkKey]bool{}, cache: map[walkKey]effective{}}
	a.materialized = options.BasePointer == "" && options.KeyScope == structuralScope && hasField(d.root, "materialization_provenance")
	a.walk(d.root, options.KeyScope, tokens, map[*node]bool{})
	slices.SortFunc(a.items, func(x, y Diagnostic) int {
		if x.Range.Start.Line != y.Range.Start.Line {
			return x.Range.Start.Line - y.Range.Start.Line
		}
		if x.Range.Start.Column != y.Range.Start.Column {
			return x.Range.Start.Column - y.Range.Start.Column
		}
		if cmp := strings.Compare(x.Code, y.Code); cmp != 0 {
			return cmp
		}
		return strings.Compare(x.Pointer, y.Pointer)
	})
	var failures []Diagnostic
	for _, d := range a.items {
		if d.Severity == "warning" {
			a.document.warnings = append(a.document.warnings, d)
		} else {
			failures = append(failures, d)
		}
	}
	if len(failures) > 0 {
		return &parseError{failures}
	}
	d.collectRanges(d.root, options.KeyScope, tokens)
	return a.expandMerges(d.root, options.KeyScope, map[*node]bool{})
}
func (a *keyAnalysis) add(code string, n *node, tokens []string, related *node, keys []string) {
	severity := "error"
	if a.options.MigrationPolicy == "accept" && (code == "sdl.noncanonical_field" || code == "sdl.noncanonical_merge") {
		severity = "warning"
	}
	d := Diagnostic{Code: code, Pointer: jsonpointer.FromTokens(tokens), Range: n.span, AuthoredKeys: keys, Severity: severity, Source: a.options.Name}
	if related != nil {
		r := related.span
		d.Related = &r
	}
	identity := fmt.Sprintf("%s/%s/%d/%d/%v", code, d.Pointer, d.Range.Start.Line, d.Range.Start.Column, d.Related)
	if !a.seen[identity] {
		a.seen[identity] = true
		a.items = append(a.items, d)
	}
}
func (a *keyAnalysis) walk(n *node, scope string, tokens []string, active map[*node]bool) {
	a.document.ranges[jsonpointer.FromTokens(tokens)] = n.span
	if active[n] {
		a.add("sdl.alias_cycle", n, tokens, nil, nil)
		return
	}
	id := walkKey{n, scope}
	if a.walked[id] || n.kind == 'v' {
		return
	}
	a.walked[id] = true
	active[n] = true
	defer delete(active, n)
	if n.kind == 's' {
		for i, c := range n.children {
			a.walk(c, scope, descend(tokens, strconv.Itoa(i)), active)
		}
		return
	}
	e := a.effective(n, scope, map[*node]bool{})
	suppressed := map[*node]bool{}
	for _, pair := range e.conflicts {
		first, last := pair[0], pair[1]
		suppressed[first.key] = true
		suppressed[last.key] = true
		a.add("sdl.mapping_key_conflict", last.key, descend(tokens, last.canonical), first.key, []string{authored(first.key), authored(last.key)})
	}
	for _, entry := range n.entries {
		a.entry(entry, scope, tokens, active, suppressed[entry.key])
	}
}
func (a *keyAnalysis) entry(e member, scope string, tokens []string, active map[*node]bool, suppress bool) {
	if e.key.merge {
		a.add("sdl.noncanonical_merge", e.key, tokens, nil, []string{"<<", "<<"})
		for _, m := range mergeSources(e.value) {
			a.walk(m, scope, tokens, active)
		}
		return
	}
	key, ok := e.key.value.(string)
	if !ok || e.key.kind != 'v' {
		a.add("sdl.mapping_key_type", e.key, descend(tokens, authored(e.key)), nil, nil)
		return
	}
	c := canonical(key, scope)
	child := descend(tokens, c)
	if scope == structuralScope && key != c && !suppress {
		a.add("sdl.noncanonical_field", e.key, child, nil, []string{key, c})
	}
	a.document.keyRanges[jsonpointer.FromTokens(child)] = e.key.span
	a.identifiers(e.key, e.value, key, tokens, child, suppress)
	a.walk(e.value, childScope(scope, c, e.value), child, active)
}
func (a *keyAnalysis) effective(n *node, scope string, active map[*node]bool) effective {
	id := walkKey{n, scope}
	if e, ok := a.cache[id]; ok {
		return e
	}
	if active[n] {
		return effective{}
	}
	active[n] = true
	defer delete(active, n)
	result := effective{}
	seen := map[string]member{}
	add := func(e member) {
		if first, ok := seen[e.canonical]; ok {
			result.conflicts = append(result.conflicts, [2]member{first, e})
		} else {
			seen[e.canonical] = e
			result.entries = append(result.entries, e)
		}
	}
	merges := a.inherit(n, scope, active, add)
	if len(merges) > 1 {
		for _, e := range merges[1:] {
			result.conflicts = append(result.conflicts, [2]member{merges[0], e})
		}
	}
	for _, e := range n.entries {
		if key, ok := e.key.value.(string); ok && !e.key.merge && e.key.kind == 'v' {
			e.canonical = canonical(key, scope)
			add(e)
		}
	}

	a.cache[id] = result
	return result
}
func (a *keyAnalysis) inherit(n *node, scope string, active map[*node]bool, add func(member)) []member {
	var merges []member
	for _, e := range n.entries {
		if !e.key.merge {
			continue
		}
		e.canonical = "<<"
		merges = append(merges, e)
		for _, src := range mergeSources(e.value) {
			if active[src] {
				continue
			}
			for _, inherited := range a.effective(src, scope, active).entries {
				add(inherited)
			}
		}
	}
	return merges
}
func mergeSources(n *node) []*node {
	if n.kind == 'm' {
		return []*node{n}
	}
	var maps []*node
	if n.kind == 's' {
		for _, c := range n.children {
			if c.kind == 'm' {
				maps = append(maps, c)
			}
		}
	}
	return maps
}
func (a *keyAnalysis) expandMerges(n *node, scope string, seen map[*node]bool) error {
	if seen[n] {
		return nil
	}
	seen[n] = true
	for _, e := range n.entries {
		if e.key.merge && !validMerge(e.value) {
			r := e.value.span
			r.End = r.Start
			return failure("sdl.parse", r, a.options)
		}
	}
	if n.kind == 'm' {
		n.entries = a.effective(n, scope, map[*node]bool{}).entries
	}
	for _, e := range n.entries {
		key, _ := e.key.value.(string)
		if err := a.expandMerges(e.value, childScope(scope, canonical(key, scope), e.value), seen); err != nil {
			return err
		}
	}
	for _, c := range n.children {
		if err := a.expandMerges(c, scope, seen); err != nil {
			return err
		}
	}
	return nil
}
func validMerge(n *node) bool {
	if n.kind == 'm' {
		return true
	}
	if n.kind != 's' {
		return false
	}
	for _, c := range n.children {
		if c.kind != 'm' {
			return false
		}
	}
	return true
}
func portable(s string) bool {
	if len(s) < 1 || len(s) > 64 || !asciiAlnum(s[0]) {
		return false
	}
	return strings.Trim(s, "abcdefghijklmnopqrstuvwxyz0123456789-_") == ""
}
func asciiAlnum(c byte) bool { return c >= 'a' && c <= 'z' || c >= '0' && c <= '9' }
func declarationPath(t []string) bool {
	if len(t) == 1 {
		return inWords(t[0], declarations)
	}
	if len(t) == 3 && ((t[0] == nodesSection && t[2] == "roles") || (t[0] == "workflows" && t[2] == "steps") || (t[0] == "variation_points" && (t[2] == "alternatives" || t[2] == "members"))) {
		return true
	}
	if len(t) == 0 || t[0] != entitiesSection || t[len(t)-1] != entitiesSection {
		return false
	}
	for i := 0; i < len(t); i += 2 {
		if t[i] != entitiesSection {
			return false
		}
	}
	return true
}
func (a *keyAnalysis) identifiers(key, value *node, name string, parent, child []string, suppress bool) {
	if declarationPath(parent) && !suppress {
		a.declaration(key, name, parent, child)
	}
	if len(child) == 1 && child[0] == "name" || scalarIdentifier(child) {
		text, ok := value.value.(string)
		if value.kind != 'v' || !ok || !portable(text) {
			a.add("sdl.identifier.invalid", value, child, nil, nil)
		}
	}
}
func (a *keyAnalysis) declaration(key *node, name string, parent, child []string) {
	local := name
	valid := portable(name)
	if a.materialized && len(parent) == 1 {
		valid = qualified(name)
		parts := strings.Split(name, ".")
		local = parts[len(parts)-1]
	}
	if !valid {
		a.add("sdl.identifier.invalid", key, child, nil, nil)
	}
	if len(parent) == 1 && parent[0] == nodesSection && len(local) > 35 {
		a.add("sdl.identifier.invalid", key, child, nil, nil)
	}
}
func qualified(name string) bool {
	if len(name) > 2048 {
		return false
	}
	parts := strings.Split(name, ".")
	if len(parts) == 0 || !portable(parts[len(parts)-1]) {
		return false
	}
	for _, part := range parts[:len(parts)-1] {
		if part != "__private" && !portable(part) {
			return false
		}
	}
	return true
}
func scalarIdentifier(t []string) bool {
	if len(t) == 3 && t[0] == forwardingSection && digits(t[1]) && t[2] == "forwarding_agent_id" {
		return true
	}
	if len(t) == 5 && digits(t[3]) && t[4] == "name" {
		return t[0] == nodesSection && t[2] == "services" || t[0] == "infrastructure" && t[2] == "acls" || t[0] == "content" && t[2] == "items"
	}
	return runtimeIdentifier(t)
}

func hasField(n *node, key string) bool {
	for _, e := range n.entries {
		if e.key.value == key {
			return true
		}
	}
	return false
}

func (d *Document) collectRanges(n *node, scope string, tokens []string) {
	d.ranges[jsonpointer.FromTokens(tokens)] = n.span
	if n.kind == 's' {
		for i, c := range n.children {
			d.collectRanges(c, scope, descend(tokens, strconv.Itoa(i)))
		}
		return
	}
	for _, e := range n.entries {
		if e.key.merge {
			for _, src := range mergeSources(e.value) {
				d.collectRanges(src, scope, tokens)
			}
			continue
		}
		key, ok := e.key.value.(string)
		if !ok || e.key.kind != 'v' {
			continue
		}
		c := canonical(key, scope)
		child := descend(tokens, c)
		d.keyRanges[jsonpointer.FromTokens(child)] = e.key.span
		d.collectRanges(e.value, childScope(scope, c, e.value), child)
	}
}

func asciiText(text string) bool {
	for _, c := range text {
		if c >= utf8.RuneSelf {
			return false
		}
	}
	return true
}
