package authoring

func (d *declarationIndex) canonicalRefs(refs []any, purpose string) (map[string]bool, error) {
	result := map[string]bool{}
	for _, ref := range concreteRefs(refs) {
		candidates := d.aliases[ref]
		count, eligible := canonicalRefCandidates(candidates, purpose, result)
		if count != 1 || !eligible {
			return nil, semanticInvalid()
		}
	}
	return result, nil
}
func refsWithin(refs, allowed map[string]bool) bool {
	for ref := range refs {
		if !allowed[ref] {
			return false
		}
	}
	return true
}
func (c materializedChecks) controlRefsWithin(refs, allowed []any, index *declarationIndex, purpose string) error {
	actual, err := index.canonicalRefs(refs, purpose)
	if err != nil {
		return err
	}
	permitted, err := index.canonicalRefs(allowed, purpose)
	if err != nil {
		return err
	}
	if !refsWithin(actual, permitted) {
		return semanticInvalid()
	}
	return nil
}

func canonicalRefCandidates(candidates map[string]declaration, purpose string, result map[string]bool) (int, bool) {
	count, eligible := 0, false
	for address, candidate := range candidates {
		inDomain, permitted := candidate.declared, candidate.declared
		if purpose == "scope" {
			inDomain, permitted = candidate.target, candidate.authority
		}
		if purpose == "target" {
			inDomain, permitted = candidate.target, candidate.target
		}
		if inDomain {
			count++
			eligible = eligible || permitted
			result[address] = true
		}
	}
	return count, eligible
}
