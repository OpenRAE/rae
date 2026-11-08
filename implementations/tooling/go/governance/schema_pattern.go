package governance

import "regexp"

const errSchemaPattern = policyInputError("schema pattern is outside the supported standard-library profile")

func compileSchemaPattern(source string) (*regexp.Regexp, error) {
	pattern, err := regexp.Compile(source)
	if err != nil {
		return nil, errSchemaPattern
	}
	return pattern, nil
}
