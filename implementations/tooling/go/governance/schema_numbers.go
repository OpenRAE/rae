package governance

import (
	"encoding/json"
	"math"
	"math/big"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"github.com/santhosh-tekuri/jsonschema/v6/kind"
)

func exactSchemaFloat(value float64) any {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return value
	}
	rational := new(big.Rat).SetFloat64(value)
	scale := rational.Denom().BitLen() - 1
	text := rational.FloatString(scale)
	if scale == 0 {
		text += ".0"
	}
	return json.Number(text)
}

// The engine validates each original keyword before this invocation-local
// extension binds its compiled arithmetic. Schema branching stays in the engine.
func schemaNumericProfile() *jsonschema.Vocabulary {
	return &jsonschema.Vocabulary{URL: "urn:raes:private:reference-numbers", Compile: compileSchemaNumbers}
}

//nolint:ireturn // The maintained compiler's extension callback has this signature.
func compileSchemaNumbers(ctx *jsonschema.CompilerContext, object map[string]any) (jsonschema.SchemaExt, error) {
	schema := ctx.Enqueue(nil)
	clampSchemaCounts(schema, object)
	divisor, ok := object["multipleOf"].(json.Number)
	if !ok || schema.MultipleOf == nil {
		return nil, nil //nolint:nilnil // No numeric keyword needs an extension.
	}
	schema.MultipleOf = nil
	return schemaMultiple{divisor}, nil
}

type schemaMultiple struct{ divisor json.Number }

func (s schemaMultiple) Validate(ctx *jsonschema.ValidatorContext, value any) {
	numerator, ok := value.(json.Number)
	if !ok {
		return
	}
	if !referenceMultiple(numerator, s.divisor) {
		got, _ := new(big.Rat).SetString(string(numerator))
		want, _ := new(big.Rat).SetString(string(s.divisor))
		ctx.AddError(&kind.MultipleOf{Got: got, Want: want})
	}
}

func referenceMultiple(numerator, divisor json.Number) bool {
	n, _ := new(big.Rat).SetString(string(numerator))
	d, _ := new(big.Rat).SetString(string(divisor))
	if n == nil || d == nil || d.Sign() == 0 {
		return false
	}
	numeratorFloat := strings.ContainsAny(string(numerator), ".eE")
	divisorFloat := strings.ContainsAny(string(divisor), ".eE")
	if !numeratorFloat && !divisorFloat {
		return new(big.Rat).Quo(n, d).IsInt()
	}
	nf, _ := n.Float64()
	df, _ := d.Float64()
	if math.IsInf(nf, 0) || math.IsInf(df, 0) {
		return false
	}
	if !divisorFloat {
		return math.Mod(nf, df) == 0
	}
	quotient := nf / df
	if math.IsInf(quotient, 0) {
		return new(big.Rat).Quo(n, d).IsInt()
	}
	return math.Trunc(quotient) == quotient
}

func clampSchemaCounts(schema *jsonschema.Schema, object map[string]any) {
	fields := map[string]**int{
		"minLength": &schema.MinLength, "maxLength": &schema.MaxLength,
		"minItems": &schema.MinItems, "maxItems": &schema.MaxItems,
		"minProperties": &schema.MinProperties, "maxProperties": &schema.MaxProperties,
		"minContains": &schema.MinContains, "maxContains": &schema.MaxContains,
	}
	maximum := int(^uint(0) >> 1)
	bound := new(big.Rat).SetInt64(int64(maximum))
	for key, field := range fields {
		number, ok := object[key].(json.Number)
		if !ok || *field == nil {
			continue
		}
		rational, valid := new(big.Rat).SetString(string(number))
		if valid && rational.Cmp(bound) > 0 {
			limit := maximum
			*field = &limit
		}
	}
}
