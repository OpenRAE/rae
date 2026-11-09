package authoring

import (
	"fmt"
	"slices"
	"strings"
)

type semanticVariationCheck struct {
	admit     bool
	model     *semanticModel
	collector *semanticCollector
	point     semanticVariation
}

func (v semanticVariationCheck) report(message string) {
	v.collector.report(semanticOwner{variationPointsField, v.point.name}, fmt.Sprintf("Variation point '%s' %s", v.point.name, message))
}
func (m *semanticModel) checkVariations(c *semanticCollector) error {
	admit := len(c.errors) == 0
	for _, point := range m.variations {
		check := semanticVariationCheck{admit: admit, model: m, collector: c, point: point}
		if err := check.checkPoint(); err != nil {
			return err
		}
	}
	if len(c.errors) == 0 {
		m.checkFamilySelection(c)
	}
	return nil
}
func (v semanticVariationCheck) checkPoint() error {
	switch v.point.Kind {
	case variationParameterKind:
		v.parameter()
	case "governed-reference":
		if err := v.references(v.point.Domain.Allowed, false); err != nil {
			return err
		}
	case variationAlternativeKind:
		if v.point.Target.Kind == "structural" {
			v.structural()
		} else {
			if err := v.references(v.memberReferences(), false); err != nil {
				return err
			}
		}
		v.relations()
	case "subset", "order":
		if err := v.references(v.memberReferences(), true); err != nil {
			return err
		}
		v.relations()
	case "logical-timing":
		v.timing()
	}
	return nil
}

func (v semanticVariationCheck) parameter() {
	variable, known := v.model.variationVariables[v.point.Target.Variable]
	if !known {
		v.report("target variable is undefined")
		return
	}
	if !v.point.Domain.hasMember() {
		v.report("domain is empty")
		return
	}
	if !v.point.Domain.matches(variable.Type) {
		v.report("domain does not match variable type")
		return
	}
	if !variable.permits(v.point.Domain) {
		v.report("domain exceeds the variable allowed_values constraint")
	}
}
func (v semanticVariationCheck) members() (map[string]semanticVariationMember, []string) {
	field, members := "members", v.point.Members
	if v.point.Kind == variationAlternativeKind {
		field, members = "alternatives", v.point.Alternatives
	}
	return members, v.model.keys(variationPointsField, v.point.name, field)
}
func (v semanticVariationCheck) memberReferences() []string {
	members, names := v.members()
	refs := make([]string, 0, len(names))
	for _, name := range names {
		refs = append(refs, members[name].Reference)
	}
	return refs
}
func (m *semanticModel) variationReferences(ref, section string) []string {
	var addresses []string
	if section == "objective-subject" {
		for address := range m.purposeReferences([]string{ref}, referenceObjectiveSubject) {
			addresses = append(addresses, address)
		}
	} else {
		for address := range m.index.aliases[ref] {
			if strings.HasPrefix(address, section+".") {
				addresses = append(addresses, address)
			}
		}
	}
	slices.Sort(addresses)
	return addresses
}
func (v semanticVariationCheck) references(candidates []string, collection bool) error {
	owner, target := variationReferenceSlot(v.point.Target.Slot)
	if collection {
		owner, target = variationCollectionSlot(v.point.Target.Slot)
	}
	ownerValid := len(v.model.variationReferences(v.point.Target.Owner, owner)) == 1
	if !ownerValid {
		v.report("target owner is undefined or has the wrong type")
	}
	for _, ref := range candidates {
		if len(v.model.variationReferences(ref, target)) != 1 {
			v.report("candidate reference is undefined or has the wrong type")
		} else if ownerValid && v.admit {
			valid, err := v.model.variationCandidate(owner, v.point.Target.Owner, v.point.Target.Slot, ref, collection)
			if err != nil {
				return err
			}
			if !valid {
				v.report("candidate is invalid for target slot")
			}
		}
	}
	return nil
}
func (v semanticVariationCheck) timing() {
	owner, kind, unit := variationTimingSlot(v.point.Target.Slot)
	if len(v.model.variationReferences(v.point.Target.Owner, owner)) != 1 {
		v.report("target owner is undefined or has the wrong type")
	}
	if v.point.Unit != unit {
		v.report("unit does not match target")
	}
	if !v.point.Domain.hasMember() {
		v.report("domain is empty")
		return
	}
	if !v.point.Domain.matches(kind) {
		v.report("domain does not match timing target type")
	}
}
