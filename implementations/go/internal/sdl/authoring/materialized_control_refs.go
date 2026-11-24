package authoring

func refsWithin(refs, allowed map[string]bool) bool {
	for ref := range refs {
		if !allowed[ref] {
			return false
		}
	}
	return true
}
