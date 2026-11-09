package source

import (
	"errors"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	"golang.org/x/text/cases"
	"golang.org/x/text/language"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const (
	budgetExceededCode    = "budget-exceeded"
	identifierInvalidCode = "sdl.identifier.invalid"
	parseCode             = "sdl.parse"
	pathInvalidCode       = "path-invalid"
	sourceLimitCode       = "sdl.source_limit"
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

var variableToken = regexp.MustCompile(`\$\{(?:(?:[a-z0-9][a-z0-9_-]{0,63}|__private)\.)*[a-z0-9][a-z0-9_-]{0,63}\}`)

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
	items        []pendingDiagnostic
	seen         map[diagnosticIdentity]bool
	walked       map[walkKey]bool
	cache        map[walkKey]effective
	built        map[*node][]member
	materialized bool
}

func analyze(d *Document, options Options) error {
	tokens, err := pointerTokens(options.BasePointer)
	if err != nil {
		return err
	}
	a := keyAnalysis{options: options, document: d, seen: map[diagnosticIdentity]bool{}, walked: map[walkKey]bool{}, cache: map[walkKey]effective{}, built: map[*node][]member{}}
	a.materialized = options.BasePointer == "" && options.KeyScope == structuralScope && hasField(d.root, "materialization_provenance")
	d.baseTokens = tokens
	a.walk(d.root, options.KeyScope, tokens, map[*node]bool{}, rootPath(tokens))
	slices.SortFunc(a.items, func(x, y pendingDiagnostic) int {
		if x.diagnostic.Range.Start.Line != y.diagnostic.Range.Start.Line {
			return x.diagnostic.Range.Start.Line - y.diagnostic.Range.Start.Line
		}
		if x.diagnostic.Range.Start.Column != y.diagnostic.Range.Start.Column {
			return x.diagnostic.Range.Start.Column - y.diagnostic.Range.Start.Column
		}
		if cmp := strings.Compare(x.diagnostic.Code, y.diagnostic.Code); cmp != 0 {
			return cmp
		}
		return comparePaths(x.path, y.path)
	})
	var failures []pendingDiagnostic
	for _, d := range a.items {
		if d.diagnostic.Severity == "warning" {
			a.document.warnings = append(a.document.warnings, d)
		} else {
			failures = append(failures, d)
		}
	}
	if len(failures) > 0 {
		return &parseError{pending: failures}
	}
	return a.expandMerges(d.root, options.KeyScope, map[*node]bool{})
}
func (a *keyAnalysis) add(code string, n *node, path *sourcePath, related *node, keys []string) {
	severity := "error"
	if a.options.MigrationPolicy == "accept" && (code == "sdl.noncanonical_field" || code == "sdl.noncanonical_merge") {
		severity = "warning"
	}
	row := pendingDiagnostic{diagnostic: Diagnostic{Code: code, Range: n.span, AuthoredKeys: keys, Severity: severity, Source: a.options.Name}, path: path}
	identity := diagnosticIdentity{code: code, path: path, start: n.span.Start}
	if related != nil {
		span := related.span
		row.diagnostic.Related = &span
		identity.related = span
		identity.hasRelated = true
	}
	if !a.seen[identity] {
		a.seen[identity] = true
		a.items = append(a.items, row)
	}
}
func (a *keyAnalysis) walk(n *node, scope string, tokens []string, active map[*node]bool, path *sourcePath) {
	if active[n] {
		a.add("sdl.alias_cycle", n, path, nil, nil)
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
			a.walk(c, scope, descend(tokens, strconv.Itoa(i)), active, path.child(strconv.Itoa(i)))
		}
		return
	}
	e := a.effective(n, scope, map[*node]bool{})
	suppressed := map[*node]bool{}
	for _, pair := range e.conflicts {
		first, last := pair[0], pair[1]
		suppressed[first.key] = true
		suppressed[last.key] = true
		a.add("sdl.mapping_key_conflict", last.key, path.child(last.canonical), first.key, []string{authored(first.key), authored(last.key)})
	}
	for _, entry := range n.entries {
		a.entry(entry, scope, tokens, active, suppressed[entry.key], path)
	}
}
func (a *keyAnalysis) entry(e member, scope string, tokens []string, active map[*node]bool, suppress bool, path *sourcePath) {
	if e.key.merge {
		a.add("sdl.noncanonical_merge", e.key, path, nil, []string{"<<", "<<"})
		for _, m := range mergeSources(e.value) {
			a.walk(m, scope, tokens, active, path)
		}
		return
	}
	key, ok := e.key.value.(string)
	if !ok || e.key.kind != 'v' {
		a.add("sdl.mapping_key_type", e.key, path.child(authored(e.key)), nil, nil)
		return
	}
	c := canonical(key, scope)
	child := descend(tokens, c)
	if scope == literalScope && !declarationPath(tokens) && variableToken.MatchString(key) {
		a.add(identifierInvalidCode, e.key, path.child(c), nil, nil)
	}
	if scope == structuralScope && key != c && !suppress {
		a.add("sdl.noncanonical_field", e.key, path.child(c), nil, []string{key, c})
	}
	a.identifiers(e.key, e.value, key, tokens, child, suppress, path.child(c))
	a.walk(e.value, childScope(scope, c, e.value), child, active, path.child(c))
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
	if n.kind == 'm' {
		entries, err := a.constructionEntries(n)
		if err != nil {
			return err
		}
		n.entries = entries
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
func (a *keyAnalysis) identifiers(key, value *node, name string, parent, child []string, suppress bool, path *sourcePath) {
	if declarationPath(parent) && !suppress {
		a.declaration(key, name, parent, path)
	}
	if len(child) == 1 && child[0] == "name" || scalarIdentifier(child) {
		text, ok := value.value.(string)
		if value.kind != 'v' || !ok || !portable(text) {
			a.add(identifierInvalidCode, value, path, nil, nil)
		}
	}
}
func (a *keyAnalysis) declaration(key *node, name string, parent []string, path *sourcePath) {
	local := name
	valid := portable(name)
	if a.materialized && len(parent) == 1 {
		valid = qualified(name)
		parts := strings.Split(name, ".")
		local = parts[len(parts)-1]
	}
	if !valid {
		a.add(identifierInvalidCode, key, path, nil, nil)
	}
	if len(parent) == 1 && parent[0] == nodesSection && len(local) > 35 {
		a.add(identifierInvalidCode, key, path, nil, nil)
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
	d.ranges[jsonpointer.FromTokens(tokens)] = n.location()
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

// The key preflight keeps authored traversal order for diagnostic pairs.
// PyYAML construction reverses groups in merge sequences, even when disjoint.
func (a *keyAnalysis) constructionEntries(n *node) ([]member, error) {
	if entries, present := a.built[n]; present {
		return entries, nil
	}
	n.locationSpan = n.span
	var inherited, local []member
	for _, entry := range n.entries {
		if !entry.key.merge {
			local = append(local, entry)
			continue
		}
		if !validMerge(entry.value) {
			span := entry.value.span
			span.End = span.Start
			return nil, failure(parseCode, span, a.options)
		}
		groups, err := a.constructionGroups(entry.value)
		if err != nil {
			return nil, err
		}
		for _, src := range mergeSources(entry.value) {
			n.locationSpan = src.location()
		}
		for _, group := range groups {
			inherited = append(inherited, group...)
		}
	}
	inherited = append(inherited, local...)
	a.built[n] = inherited
	return inherited, nil
}
func (a *keyAnalysis) constructionGroups(value *node) ([][]member, error) {
	sources := mergeSources(value)
	groups := make([][]member, 0, len(sources))
	for _, src := range sources {
		entries, err := a.constructionEntries(src)
		if err != nil {
			return nil, err
		}
		groups = append(groups, entries)
	}
	if value.kind == 's' {
		slices.Reverse(groups)
	}
	return groups, nil
}
