package admission

import "testing"

// CI runs this target; ordinary local runs select the recorded syntax cases.
func FuzzMetadataPatternSyntax(f *testing.F) {
	for _, source := range []string{"", "[", "(?P<id>a)(?P=id)", "(?<=a|bb)c", "(?x)a # comment\nb", "(a)?(?(1)b|c)", "a{4294967295}"} {
		f.Add(source)
	}
	f.Fuzz(func(_ *testing.T, source string) {
		if len(source) > 4096 {
			return
		}
		pythonPatternValid(source)
	})
}
