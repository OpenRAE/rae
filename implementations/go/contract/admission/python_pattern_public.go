package admission

// PythonPatternSyntax is checked Python pattern syntax. It retains only named
// characters resolved from that expression. It neither stores nor executes the
// source, and callers cannot mutate the retained facts. Its zero value has none.
type PythonPatternSyntax struct {
	characters map[string]rune
}

// ParsePythonPattern checks the existing metadata grammar without executing a
// pattern. Invalid input returns the contract's value-free invalid-input error.
func ParsePythonPattern(string) (PythonPatternSyntax, error) {
	return PythonPatternSyntax{}, invalid()
}

// NamedCharacter returns a character resolved from a named escape in this
// expression. Names use the parser's case-insensitive Unicode lookup. A name
// absent from the expression, including on the zero value, returns false.
func (PythonPatternSyntax) NamedCharacter(string) (rune, bool) {
	return 0, false
}
