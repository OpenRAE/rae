package admission

import (
	"maps"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type materializationComposer struct {
	identities map[string][]string
	remaining  int
}

// ComposeMaterializationContent combines independently derived common-content
// projections. The returned value still requires native prospective admission.
func ComposeMaterializationContent(v *Validator, source, preceding, local MaterializationCompilation) (Fragment, error) { //nolint:ireturn // The native relation returns the declared opaque value handle.
	if v == nil {
		return nil, invalid()
	}
	inputs := []MaterializationCompilation{source, preceding, local}
	content := make([]*materializationCompiled, len(inputs))
	composer := materializationComposer{identities: map[string][]string{}, remaining: 100000}
	for index, input := range inputs {
		compiled, err := materializationContentInput(input)
		if err != nil {
			return nil, err
		}
		content[index] = compiled
		if err := composer.mergeProfiles(compiled.identities); err != nil {
			return nil, err
		}
	}
	combined, err := composer.compose(materializationOperand{value: content[0].full, present: true}, materializationOperand{value: content[1].full, present: true}, materializationOperand{value: content[2].full, present: true}, nil)
	if err != nil {
		return nil, err
	}
	return AdmitFragment(v, RealizationValue, combined.value, ingress.Limits{MaxBytes: value.MaterializationBytes, MaxDepth: 64})
}

// FullDocument is independently supplied native common-content phase data.
// The caller binds Document to its actual source and owns native construction;
// this primitive checks bounded comparison data without promoting its phase.
func materializationContentInput(input MaterializationCompilation) (*materializationCompiled, error) {
	limits := ingress.Limits{MaxBytes: value.MaterializationBytes, MaxDepth: 64}
	document, err := ingress.Parse(input.Document, limits, ingress.Object)
	if err != nil || value.Validate(document, value.Runtime()) != nil {
		return nil, invalid()
	}
	full, err := ingress.Parse(input.FullDocument, limits, ingress.Object)
	if err != nil || value.Validate(full, value.Runtime()) != nil {
		return nil, invalid()
	}
	if len(input.CollectionIdentities) > 16384 || materializationIdentityProfiles(input.CollectionIdentities) != nil || len(input.OrdinarySelections) > 16384 || !materializationOrdinaryBound(input.OrdinarySelections) {
		return nil, invalid()
	}
	common := maps.Clone(object(full))
	delete(common, "instantiation_provenance")
	delete(common, "materialization_provenance")
	identities := make(map[string][]string, len(input.CollectionIdentities))
	for path, fields := range input.CollectionIdentities {
		identities[path] = slices.Clone(fields)
	}
	return &materializationCompiled{document: document, full: common, identities: identities, ordinary: maps.Clone(input.OrdinarySelections)}, nil
}

func (c *materializationComposer) mergeProfiles(profiles map[string][]string) error {
	for path, fields := range profiles {
		if prior, present := c.identities[path]; present && !slices.Equal(prior, fields) {
			return invalid()
		}
		c.identities[path] = fields
	}
	return nil
}

func materializationOperandEqual(a, b materializationOperand) bool {
	return a.present == b.present && (!a.present || equal(a.value, b.value))
}

func (c *materializationComposer) compose(base, prior, local materializationOperand, path []string) (materializationOperand, error) {
	c.remaining--
	if c.remaining < 0 {
		return materializationOperand{}, invalid()
	}
	if materializationOperandEqual(base, local) {
		return prior, nil
	}
	if materializationOperandEqual(base, prior) {
		return local, nil
	}
	if object(base.value) != nil && object(prior.value) != nil && object(local.value) != nil {
		return c.mapping(base.value, prior.value, local.value, path)
	}
	if fields := materializationCollectionFields(path, c.identities); len(fields) > 0 {
		return c.collection(base.value, prior.value, local.value, path, fields)
	}
	return materializationOperand{}, invalid()
}

func (c *materializationComposer) mapping(base, prior, local any, path []string) (materializationOperand, error) {
	keys := map[string]bool{}
	for _, input := range []any{base, prior, local} {
		for key := range object(input) {
			keys[key] = true
		}
	}
	merged := map[string]any{}
	for _, key := range slices.Sorted(maps.Keys(keys)) {
		original, hasOriginal := object(base)[key]
		preceding, hasPreceding := object(prior)[key]
		proposed, hasProposed := object(local)[key]
		selected, err := c.compose(materializationOperand{value: original, present: hasOriginal}, materializationOperand{value: preceding, present: hasPreceding}, materializationOperand{value: proposed, present: hasProposed}, append(slices.Clone(path), key))
		if err != nil {
			return materializationOperand{}, err
		}
		if selected.present {
			merged[key] = selected.value
		}
	}
	return materializationOperand{value: merged, present: true}, nil
}

func (c *materializationComposer) collection(base, prior, local any, path, fields []string) (materializationOperand, error) {
	index := make([]map[string]materializationOperand, 3)
	order := []string{}
	seen := map[string]bool{}
	for i, input := range []any{prior, local, base} {
		rows, ok := input.([]any)
		if !ok {
			return materializationOperand{}, invalid()
		}
		indexed, err := materializationIndexed(rows, fields, path)
		if err != nil {
			return materializationOperand{}, err
		}
		index[i] = indexed
		for _, key := range materializationIndexOrder(indexed, len(rows)) {
			if !seen[key] {
				order = append(order, key)
				seen[key] = true
			}
		}
	}
	return c.members(index[2], index[0], index[1], order, path)
}

func materializationIndexOrder(index map[string]materializationOperand, length int) []string {
	order := make([]string, length)
	for key, item := range index {
		position, err := strconv.Atoi(item.path[len(item.path)-1])
		if err != nil || position < 0 || position >= length {
			panic("admission: native materialization index is invalid")
		}
		order[position] = key
	}
	return order
}

func (c *materializationComposer) members(base, prior, local map[string]materializationOperand, order, path []string) (materializationOperand, error) {
	merged := []any{}
	for _, key := range order {
		selected, err := c.compose(base[key], prior[key], local[key], append(slices.Clone(path), strconv.Itoa(len(merged))))
		if err != nil {
			return materializationOperand{}, err
		}
		if selected.present {
			merged = append(merged, selected.value)
		}
	}
	return materializationOperand{value: merged, present: true}, nil
}
