package admission

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func sdlNodePresence(v any) error {
	for _, references := range object(at(v, "inventory")) {
		for _, reference := range array(references) {
			if !materializationQualified(text(reference)) {
				return invalid()
			}
		}
	}
	return nil
}

func sdlAlternative(v any) error {
	seen := map[string]bool{}
	for _, member := range object(at(v, "alternatives")) {
		key, err := jsonDigest(sdlAlternativeValue(member))
		if err != nil || seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}

func sdlAlternativeValue(v any) any {
	switch stringAt(v, termKind) {
	case "runtime-inventory":
		return sdlSortedTexts(at(v, "references"))
	case "declaration-presence":
		return map[string]any{termPresent: at(v, termPresent)}
	case "resource-consumers":
		rows := make([][]string, 0, len(array(at(v, "consumers"))))
		for _, consumer := range array(at(v, "consumers")) {
			rows = append(rows, []string{stringAt(consumer, "node"), stringAt(consumer, "mount_destination")})
		}
		slices.SortFunc(rows, slices.Compare[[]string])
		return rows
	case "node-presence":
		inventory := map[string]any{}
		for slot, refs := range object(at(v, "inventory")) {
			inventory[slot] = sdlSortedTexts(refs)
		}
		return map[string]any{termPresent: at(v, termPresent), "inventory": inventory}
	default:
		return at(v, "reference")
	}
}

func sdlSortedTexts(v any) []string {
	result := stringsOf(v)
	if result == nil {
		result = []string{}
	}
	slices.Sort(result)
	return result
}

func sdlOrder(v any) error {
	members := object(at(v, "members"))
	refs := map[string]bool{}
	for _, member := range members {
		ref := stringAt(member, "reference")
		if refs[ref] {
			return invalid()
		}
		refs[ref] = true
	}
	edges, err := sdlOrderEdges(v, members)
	if err != nil || graph.HasCycle(edges) {
		return invalid()
	}
	fixed, err := sdlOrderFixed(v, members)
	if err != nil || len(fixed) == 0 {
		return err
	}
	names := slices.Sorted(maps.Keys(members))
	return require(newSDLOrderSearch(names, edges, fixed).hasWitness())
}

func sdlOrderEdges(v any, members map[string]any) (map[string][]string, error) {
	if !uniqueRows(at(v, "precedence"), "before", "after") {
		return nil, invalid()
	}
	edges := map[string][]string{}
	for _, edge := range array(at(v, "precedence")) {
		before, after := stringAt(edge, "before"), stringAt(edge, "after")
		if members[before] == nil || members[after] == nil {
			return nil, invalid()
		}
		edges[after] = append(edges[after], before)
	}
	return edges, nil
}

func sdlOrderFixed(v any, members map[string]any) (map[string]int, error) {
	result, occupied := map[string]int{}, map[int]bool{}
	for name, raw := range object(at(v, "fixed_positions")) {
		position, ok := integer(raw)
		if !ok || members[name] == nil || position < 0 || position >= len(members) || occupied[position] {
			return nil, invalid()
		}
		result[name], occupied[position] = position, true
	}
	return result, nil
}
