package parity

// runners maps the key of each command that the Go implementation covers to
// its runner. Each Go port adds the commands that it implements.
func runners() map[string]Runner {
	return map[string]Runner{}
}
