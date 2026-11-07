package admission

import (
	"regexp"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
)

var (
	sdlAptSuite     = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9.+_~:-]{0,127}\z`)
	sdlAptComponent = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9.+_~-]{0,127}\z`)
	sdlAptName      = regexp.MustCompile(`^[a-z0-9][a-z0-9+.-]{0,127}\z`)
	sdlAptVersion   = regexp.MustCompile(`^[0-9][A-Za-z0-9.+:~_-]{0,255}\z`)
)

func sdlHTTPS(value string) bool {
	return variableRef(value) || strings.HasPrefix(value, "https:") && urisafety.Check(value, urisafety.Options{ForbidFragment: true}) == nil
}
func sdlAptRepository(v any) error {
	suite := stringAt(v, "suite")
	if !sdlHTTPS(stringAt(v, "uri")) || !variableRef(suite) && !sdlAptSuite.MatchString(suite) {
		return invalid()
	}
	for _, component := range stringsOf(at(v, "components")) {
		if !variableRef(component) && !sdlAptComponent.MatchString(component) {
			return invalid()
		}
	}
	return nil
}
func sdlPackage(v any) error {
	if at(v, "repository") == nil {
		return nil
	}
	for field, pattern := range map[string]*regexp.Regexp{termName: sdlAptName, termVersion: sdlAptVersion} {
		value := stringAt(v, field)
		if !variableRef(value) && !pattern.MatchString(value) {
			return invalid()
		}
	}
	return require(stringAt(v, "manager") == "apt")
}
