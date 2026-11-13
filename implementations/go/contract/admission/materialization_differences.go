package admission

import (
	"maps"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

type materializationOperand struct {
	value   any
	present bool
	path    []string
}
type materializationDiff struct {
	identities map[string][]string
	origins    []any
	remaining  int
}

func materializationOrigins(original, current *materializationCompiled) error {
	profiles := maps.Clone(original.identities)
	for path, fields := range current.identities {
		if prior, ok := profiles[path]; ok && !slices.Equal(prior, fields) {
			return invalid()
		}
		profiles[path] = fields
	}
	d := materializationDiff{identities: profiles, remaining: 100000}
	left, right := maps.Clone(object(original.full)), maps.Clone(object(current.full))
	delete(left, "instantiation_provenance")
	delete(right, "materialization_provenance")
	if err := d.walk(materializationOperand{value: left, present: true}, materializationOperand{value: right, present: true}); err != nil {
		return err
	}
	expected, err := materializationOriginSet(d.origins)
	if err != nil {
		return err
	}
	actual, err := materializationOriginSet(array(at(current.full, "materialization_provenance", "origins")))
	if err != nil {
		return err
	}
	return require(equal(expected, actual))
}

func materializationOriginSet(rows []any) (map[string]bool, error) {
	result := map[string]bool{}
	for _, row := range rows {
		normalized := map[string]any{"field_pointer": at(row, "field_pointer"), "source_pointer": at(row, "source_pointer"), "change": at(row, "change"), "origin": at(row, "origin")}
		key, err := jsonDigest(normalized)
		if err != nil {
			return nil, err
		}
		result[key] = true
	}
	return result, nil
}

func (d *materializationDiff) walk(a, b materializationOperand) error {
	d.remaining--
	if d.remaining < 0 {
		return invalid()
	}
	if a.present && b.present {
		if object(a.value) != nil && object(b.value) != nil {
			return d.mapping(a, b)
		}
		left, lok := a.value.([]any)
		right, rok := b.value.([]any)
		if lok && rok {
			return d.sequence(a, b, left, right)
		}
		if equal(a.value, b.value) {
			return nil
		}
	}
	change := "selected"
	path := b.path
	if !a.present {
		change = termAdded
	} else if !b.present {
		change = "removed"
		path = a.path
	}
	var source any
	if a.present {
		source = jsonpointer.FromTokens(a.path)
	}
	d.origins = append(d.origins, map[string]any{"change": change, "field_pointer": jsonpointer.FromTokens(path), "source_pointer": source, "origin": termBackendRealized})
	return nil
}

func (d *materializationDiff) mapping(a, b materializationOperand) error {
	keys := mapKeys(a.value)
	for key := range object(b.value) {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	keys = slices.Compact(keys)
	for _, key := range keys {
		left, lok := object(a.value)[key]
		right, rok := object(b.value)[key]
		if err := d.walk(materializationOperand{left, lok, append(slices.Clone(a.path), key)}, materializationOperand{right, rok, append(slices.Clone(b.path), key)}); err != nil {
			return err
		}
	}
	return nil
}

func (d *materializationDiff) sequence(a, b materializationOperand, left, right []any) error {
	fields := materializationCollectionFields(b.path, d.identities)
	if len(fields) > 0 {
		return d.keyed(a, b, left, right, fields)
	}
	for index := range max(len(left), len(right)) {
		x := materializationOperand{present: index < len(left), path: append(slices.Clone(a.path), strconv.Itoa(index))}
		y := materializationOperand{present: index < len(right), path: append(slices.Clone(b.path), strconv.Itoa(index))}
		if x.present {
			x.value = left[index]
		}
		if y.present {
			y.value = right[index]
		}
		if err := d.walk(x, y); err != nil {
			return err
		}
	}
	return nil
}

func materializationCollectionFields(path []string, profiles map[string][]string) []string {
	if fields := profiles[jsonpointer.FromTokens(path)]; len(fields) > 0 {
		return fields
	}
	if len(path) == 3 && path[0] == termNodes && path[2] == "services" {
		return []string{termName}
	}
	var family string
	var relative []string
	switch {
	case len(path) > 0 && path[0] == termForwardingAgents:
		family, relative = termForwardingAgents, path[1:]
	case len(path) >= 4 && path[0] == termNodes && path[2] == termRuntime:
		family, relative = path[3], path[4:]
	default:
		return nil
	}
	identity := sdlrules.RuntimeCollectionIdentity(strings.ReplaceAll(family, "_", "-"), jsonpointer.FromTokens(relative))
	if identity == "" {
		return nil
	}
	return []string{identity}
}

func materializationIndexed(items []any, fields, path []string) (map[string]materializationOperand, error) {
	result := map[string]materializationOperand{}
	for index, item := range items {
		identity := map[string]any{}
		for _, field := range fields {
			value, ok := object(item)[field]
			if !ok {
				return nil, invalid()
			}
			identity[field] = value
		}
		key, err := jsonDigest(identity)
		if err != nil {
			return nil, err
		}
		if _, ok := result[key]; ok {
			return nil, invalid()
		}
		result[key] = materializationOperand{item, true, append(slices.Clone(path), strconv.Itoa(index))}
	}
	return result, nil
}

func (d *materializationDiff) keyed(a, b materializationOperand, left, right []any, fields []string) error {
	x, err := materializationIndexed(left, fields, a.path)
	if err != nil {
		return err
	}
	y, err := materializationIndexed(right, fields, b.path)
	if err != nil {
		return err
	}
	keys := make([]string, 0, len(x)+len(y))
	for key := range x {
		keys = append(keys, key)
	}
	for key := range y {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	keys = slices.Compact(keys)
	for _, key := range keys {
		av, aok := x[key]
		bv, bok := y[key]
		if !aok {
			av = materializationOperand{path: append(slices.Clone(a.path), "0")}
		}
		if !bok {
			bv = materializationOperand{path: append(slices.Clone(b.path), "0")}
		}
		if err = d.walk(av, bv); err != nil {
			return err
		}
	}
	return nil
}
