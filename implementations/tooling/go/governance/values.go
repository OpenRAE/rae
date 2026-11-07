package governance

import (
	"encoding/json"
	"sort"
)

const fieldTypeRule = "field-type"
const policyField = "policy"
const adrRefsField = "adr_refs"
const authorityField = "authority"
const provenanceField = "provenance"

const rootLocation = "<root>"

const trueLiteral = "true"
const titleField = "title"
const sha256Algorithm = "sha256"

// Callers use this only for JSON objects or model-validated string-key maps.
func sortedMappingKeys(m *mapping) []string {
	if m == nil {
		return nil
	}
	keys := make([]string, len(m.keys))
	for i, key := range m.keys {
		keys[i], _ = key.(string)
	}
	sort.Strings(keys)
	return keys
}

func renderFinding(f Finding) string {
	message := "[" + f.RuleID + "] "
	if f.Path != nil && *f.Path != "" {
		message += *f.Path + ": "
	}
	return message + f.Message
}

func stringList(value any, nonempty bool) ([]string, bool) {
	items, ok := value.([]any)
	if !ok {
		return nil, false
	}
	strings := make([]string, len(items))
	for i, item := range items {
		value, ok := item.(string)
		if !ok || nonempty && value == "" {
			return nil, false
		}
		strings[i] = value
	}
	return strings, true
}

func pythonType(value any) string {
	switch value.(type) {
	case nil:
		return "NoneType"
	case bool:
		return "bool"
	case string:
		return "str"
	case json.Number:
		return "int"
	case float64:
		return "float"
	case *mapping:
		return "dict"
	case []any, []string:
		return "list"
	case yamlDate:
		return "date"
	case yamlTimestamp:
		return "datetime"
	case yamlBinary:
		return "bytes"
	case yamlSet:
		return "set"
	case yamlTuple:
		return "tuple"
	default:
		return "object"
	}
}

func pythonStr(value any) string {
	if v, ok := value.(string); ok {
		return v
	}
	if v, ok := value.(yamlDate); ok {
		return v.Format("2006-01-02")
	}
	return pythonRepr(value)
}

func finding(rule, message, path string) Finding {
	f := Finding{RuleID: rule, Message: message}
	if path != "" {
		f.Path = &path
	}
	return f
}

func finish(findings []Finding) Report {
	if findings == nil {
		findings = []Finding{}
	}
	status := 0
	if len(findings) > 0 {
		status = 1
	}
	return Report{Findings: findings, ExitCode: status}
}

func sortFindings(findings []Finding) {
	sort.SliceStable(findings, func(i, j int) bool {
		a, b := findings[i], findings[j]
		ap, bp := "", ""
		if a.Path != nil {
			ap = *a.Path
		}
		if b.Path != nil {
			bp = *b.Path
		}
		if ap != bp {
			return ap < bp
		}
		if a.RuleID != b.RuleID {
			return a.RuleID < b.RuleID
		}
		return a.Message < b.Message
	})
}

const pythonIdentifier = "identifier"
const pythonStringNode = "string"
const nullLiteral = "null"
const numberKind = "number"
const repoFullCheck = "full"

const pythonParentheses = "parenthesized_expression"
const deprecatedStatus = "deprecated"
