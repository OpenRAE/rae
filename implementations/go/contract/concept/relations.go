package concept

import (
	"cmp"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// Relation is one behavioral-relation definition and the bindings that a
// claim about it requires.
type Relation struct {
	ID                                  string
	ProjectionRequired, ProfileRequired bool
}

// RelationCatalog is one exact revision of the behavioral-relation taxonomy.
// Relations are in ID order.
type RelationCatalog struct {
	TaxonomyID, TaxonomyRevision string
	Relations                    []Relation
}

type relationWire struct {
	TaxonomyID       string `json:"taxonomy_id"`
	TaxonomyRevision string `json:"taxonomy_revision"`
	Relations        map[string]struct {
		ProjectionRequired bool `json:"projection_required"`
		ProfileRequired    bool `json:"relation_parameter_profile_required"`
	} `json:"relations"`
}

func decodeRelationCatalog(data []byte) (RelationCatalog, error) {
	var wire relationWire
	if err := decode(data, &wire); err != nil {
		return RelationCatalog{}, err
	}
	catalog := RelationCatalog{TaxonomyID: wire.TaxonomyID, TaxonomyRevision: wire.TaxonomyRevision}
	for id, row := range wire.Relations {
		catalog.Relations = append(catalog.Relations, Relation{ID: id, ProjectionRequired: row.ProjectionRequired, ProfileRequired: row.ProfileRequired})
	}
	slices.SortFunc(catalog.Relations, func(x, y Relation) int { return cmp.Compare(x.ID, y.ID) })
	return catalog, nil
}

// decodeRelations keys each packaged catalog by its exact revision. A history
// file must hold the revision of its registry entry, and the current catalog
// must not repeat a history revision.
func (a *Authority) decodeRelations(documents map[string][]byte) error {
	current, err := decodeRelationCatalog(documents[pathRelations])
	if err != nil {
		return err
	}
	a.current = current.TaxonomyRevision
	a.relations = map[string]RelationCatalog{current.TaxonomyRevision: current}
	for _, revision := range historyRevisions() {
		catalog, err := decodeRelationCatalog(documents[relationHistoryDir+revision+".json"])
		if err != nil {
			return err
		}
		if _, repeated := a.relations[revision]; repeated || catalog.TaxonomyRevision != revision {
			return damaged()
		}
		a.relations[revision] = catalog
	}
	return nil
}

// Relation returns the relation with the ID.
func (c RelationCatalog) Relation(id string) (Relation, bool) {
	index, found := slices.BinarySearchFunc(c.Relations, id, func(r Relation, id string) int { return cmp.Compare(r.ID, id) })
	if !found {
		return Relation{}, false
	}
	return c.Relations[index], true
}

// RelationCatalog returns the packaged catalog of the exact taxonomy
// revision. An unpackaged revision is a NotFound fault.
func (a *Authority) RelationCatalog(revision string) (RelationCatalog, error) {
	catalog, ok := a.relations[revision]
	if !ok {
		return RelationCatalog{}, fault.New(fault.NotFound, "behavioral-authority-unsupported", nil)
	}
	return catalog.copy(), nil
}

// CurrentRelationCatalog returns the current taxonomy revision.
func (a *Authority) CurrentRelationCatalog() RelationCatalog { return a.relations[a.current].copy() }

func (c RelationCatalog) copy() RelationCatalog {
	c.Relations = slices.Clone(c.Relations)
	return c
}
