package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"

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

// Collection metadata is shared with native SDL reference indexing.
// Only these selected families use the owner-wide local identity namespace.
func sdlFamilyIdentities(collection string) func(any) error {
	for _, family := range sdlrules.RuntimeFamilies() {
		if family.Collection != collection {
			continue
		}
		specs := make([][2]string, len(family.Children))
		for i, child := range family.Children {
			specs[i] = [2]string{child.Collection, child.Identity}
		}
		rootID := sdlSymbol.MatchString
		if collection == termForwardingAgents {
			rootID = materializationQualified
		}
		return sdlLocalIdentityRule(family.Identity, rootID, specs...)
	}
	panic("unregistered runtime identity rule")
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
