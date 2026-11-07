package admission

func sdlUniqueLists(fields ...string) func(any) error {
	return func(v any) error { return require(fieldsUnique(v, fields...)) }
}
func sdlUniqueCollections(specs ...[2]string) func(any) error {
	return func(v any) error {
		for _, spec := range specs {
			if !sdlUniqueKey(at(v, spec[0]), spec[1], false) {
				return invalid()
			}
		}
		return nil
	}
}
func sdlLocalIdentities(owner string, specs ...[2]string) func(any) error {
	return sdlLocalIdentityRule(owner, sdlSymbol.MatchString, specs...)
}
func sdlLocalIdentityRule(owner string, rootID func(string) bool, specs ...[2]string) func(any) error {
	return func(v any) error {
		if !rootID(stringAt(v, owner)) {
			return invalid()
		}
		seen := map[string]bool{stringAt(v, owner): true}
		for _, spec := range specs {
			for _, row := range array(at(v, spec[0])) {
				id := stringAt(row, spec[1])
				if !sdlSymbolField(row, spec[1]) || seen[id] {
					return invalid()
				}
				seen[id] = true
			}
		}
		return nil
	}
}
