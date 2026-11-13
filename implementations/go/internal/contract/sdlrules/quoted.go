package sdlrules

import "github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"

// quoted preserves the existing SDL diagnostic spelling through its shared owner.
func quoted(value string) string { return pyrepr.Quote(value) }
