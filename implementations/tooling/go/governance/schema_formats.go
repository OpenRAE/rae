package governance

import (
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"golang.org/x/net/idna"
)

const errSchemaFormat = policyInputError("value does not match the frozen schema format profile")

var schemaTimePattern = regexp.MustCompile(`^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:[.,][0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])\n?\z`)
var schemaDateTimePrefix = regexp.MustCompile(`^[0-9]{4}-(?:0[1-9]|1[0-2])-[0-3][0-9][Tt]`)

func frozenSchemaFormats(compiler *jsonschema.Compiler) {
	// The pinned Python environment does not install these optional assertions.
	for _, name := range []string{"hostname", "duration", "period", "uri", "iri", "uri-reference", "iri-reference", "uri-template", "json-pointer", "relative-json-pointer", "semver"} {
		compiler.RegisterFormat(&jsonschema.Format{Name: name, Validate: ignoreSchemaFormat})
	}
	for _, name := range []string{"email", "idn-email"} {
		compiler.RegisterFormat(&jsonschema.Format{Name: name, Validate: schemaEmailFormat})
	}
	for name, validate := range map[string]func(any) error{"date": schemaDateFormat, "time": schemaTimeFormat, "date-time": schemaDateTimeFormat, "idn-hostname": schemaIDNFormat} {
		compiler.RegisterFormat(&jsonschema.Format{Name: name, Validate: validate})
	}
}
func ignoreSchemaFormat(any) error { return nil }
func schemaEmailFormat(value any) error {
	if text, ok := value.(string); ok && !strings.Contains(text, "@") {
		return errSchemaFormat
	}
	return nil
}
func schemaDateFormat(value any) error {
	text, ok := value.(string)
	if !ok {
		return nil
	}
	parsed, err := time.Parse(time.DateOnly, text)
	if err != nil || parsed.Year() == 0 {
		return errSchemaFormat
	}
	return nil
}
func schemaTimeFormat(value any) error {
	text, ok := value.(string)
	if !ok || !schemaTimePattern.MatchString(text) {
		return errSchemaFormat
	}
	return nil
}
func schemaDateTimeFormat(value any) error {
	text, ok := value.(string)
	if !ok {
		return nil
	}
	if !schemaDateTimePrefix.MatchString(text) {
		return errSchemaFormat
	}
	year, _ := strconv.Atoi(text[:4])
	month, _ := strconv.Atoi(text[5:7])
	day, _ := strconv.Atoi(text[8:10])
	date := time.Date(year, time.Month(month), day, 0, 0, 0, 0, time.UTC)
	if date.Day() != day || date.Month() != time.Month(month) {
		return errSchemaFormat
	}
	return schemaTimeFormat(text[11:])
}
func schemaIDNFormat(value any) error {
	text, ok := value.(string)
	if !ok {
		return nil
	}
	for _, r := range text {
		if !unicode.Is(pythonAssigned(), r) {
			return errSchemaFormat
		}
	}
	text = strings.Map(func(r rune) rune {
		switch {
		case r >= 'A' && r <= 'Z':
			return r + ('a' - 'A')
		case r == '\u3002' || r == '\uff0e' || r == '\uff61':
			return '.'
		default:
			return r
		}
	}, text)
	text = strings.TrimSuffix(text, ".")
	profile := idna.New(idna.ValidateForRegistration())
	_, err := profile.ToASCII(text)
	if err != nil {
		return errSchemaFormat
	}
	return nil
}

func candidateDialect(value any, python bool) string {
	if python {
		return defaultMetaschema
	}
	dialect, _ := object(value).get("$schema").(string)
	plain := strings.TrimSuffix(dialect, "#")
	for _, scheme := range []string{"http://", "https://"} {
		for _, draft := range []string{"draft-04", "draft-06", "draft-07", "draft/2019-09", "draft/2020-12"} {
			if plain == scheme+"json-schema.org/"+draft+"/schema" {
				return dialect
			}
		}
	}
	return defaultMetaschema
}
