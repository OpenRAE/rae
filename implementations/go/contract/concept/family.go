package concept

import (
	"maps"
	"slices"
)

// Family is one concept family of concept-families-v1. Authority is empty
// for a family that names no authority.
type Family struct{ ID, Authority, Provenance string }

func (a *Authority) decodeFamilies(documents map[string][]byte) error {
	var wire struct {
		Families map[string]struct {
			Authority  string `json:"authority"`
			Provenance string `json:"provenance"`
		} `json:"families"`
	}
	if err := decode(documents[pathFamilies], &wire); err != nil {
		return err
	}
	a.families = make(map[string]Family, len(wire.Families))
	for id, row := range wire.Families {
		a.families[id] = Family{ID: id, Authority: row.Authority, Provenance: row.Provenance}
	}
	return nil
}

// Family returns the concept family with the catalog key.
func (a *Authority) Family(id string) (Family, bool) {
	family, ok := a.families[id]
	return family, ok
}

// Families returns every concept family in ID order.
func (a *Authority) Families() []Family {
	families := make([]Family, 0, len(a.families))
	for _, id := range slices.Sorted(maps.Keys(a.families)) {
		families = append(families, a.families[id])
	}
	return families
}
