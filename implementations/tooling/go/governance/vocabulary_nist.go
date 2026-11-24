package governance

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"fmt"
	"io"
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

const spreadsheetNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

var nistCategoryPattern = regexp.MustCompile(`^(.+) \(((?:DE|RS|RC)\.[A-Z]{2})\): (.+)\z`)

func compareNISTBytes(profile vocabularyProfile, source *mapping, data []byte) ([]string, error) {
	categories, err := extractNISTCategories(data)
	if err != nil {
		return nil, err
	}
	raw, _ := source.get("categories").([]any)
	messages := []string{}
	if !publicationEqual(categories, raw) {
		messages = append(messages, profile.path+": category snapshot differs from the current NIST CSF 2.0 Core export")
	}
	encoded, err := canonicalJSON(schemaTransport(categories), true)
	if err != nil {
		return nil, err
	}
	if "sha256:"+fmt.Sprintf("%x", sha256.Sum256(encoded)) != source.get(sourceDigestField) {
		messages = append(messages, profile.path+": canonical remote digest differs from source_digest")
	}
	return messages, nil
}

func extractNISTCategories(data []byte) ([]any, error) {
	rows, err := nistWorkbookRows(data)
	if err != nil {
		return nil, err
	}
	terms := map[string]string{"DE.CM": "continuous-monitoring", "DE.AE": "adverse-event-analysis", "RS.MA": "incident-management", "RS.AN": "incident-analysis", "RS.CO": "incident-response-reporting-and-communication", "RS.MI": "incident-mitigation", "RC.RP": "incident-recovery-plan-execution", "RC.CO": "incident-recovery-communication"}
	function := ""
	categories := []any{}
	for _, row := range rows {
		if row["A"] != "" {
			name, _, _ := strings.Cut(row["A"], " (")
			function = nistFunctionTitle(name)
		}
		match := nistCategoryPattern.FindStringSubmatch(row["B"])
		if match == nil || terms[match[2]] == "" {
			continue
		}
		category := newMapping()
		category.set("category_id", match[2])
		category.set("term_id", terms[match[2]])
		category.set(titleField, match[1])
		category.set(descriptionField, match[3])
		category.set("function", function)
		categories = append(categories, category)
	}
	return categories, nil
}

func nistWorkbookRows(data []byte) ([]map[string]string, error) {
	workbook, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, policyInputError("NIST snapshot is not a readable ZIP workbook")
	}
	sharedRoot, err := nistWorkbookXML(workbook, "xl/sharedStrings.xml")
	if err != nil {
		return nil, err
	}
	shared := []string{}
	for _, item := range sharedRoot.elements(spreadsheetNamespace, "si", false) {
		var text strings.Builder
		for _, node := range item.elements(spreadsheetNamespace, "t", true) {
			text.WriteString(node.text.String())
		}
		shared = append(shared, text.String())
	}
	sheet, err := nistWorkbookXML(workbook, "xl/worksheets/sheet2.xml")
	if err != nil {
		return nil, err
	}
	rows := []map[string]string{}
	for _, row := range sheet.elements(spreadsheetNamespace, "row", true) {
		values, err := nistRowValues(row, shared)
		if err != nil {
			return nil, err
		}
		rows = append(rows, values)
	}
	return rows, nil
}

func nistRowValues(row *xmlElement, shared []string) (map[string]string, error) {
	values := map[string]string{}
	for _, cell := range row.elements(spreadsheetNamespace, "c", false) {
		value, err := nistCellValue(cell, shared)
		if err != nil {
			return nil, err
		}
		if coordinate := cell.attribute("r"); coordinate != "" {
			column, _ := utf8.DecodeRuneInString(coordinate)
			values[string(column)] = value
		}
	}
	return values, nil
}

func nistCellValue(cell *xmlElement, shared []string) (string, error) {
	nodes := cell.elements(spreadsheetNamespace, "v", false)
	value := ""
	if len(nodes) > 0 {
		value = nodes[0].text.String()
	}
	if cell.attribute("t") != "s" || value == "" {
		return value, nil
	}
	integer, valid := extractionInteger(value)
	if !valid {
		return "", policyInputError("NIST shared-string index is invalid")
	}
	index, err := integer.Int64()
	if err != nil {
		return "", policyInputError("NIST shared-string index is outside the workbook")
	}
	if index < 0 {
		index += int64(len(shared))
	}
	if index < 0 || index >= int64(len(shared)) {
		return "", policyInputError("NIST shared-string index is outside the workbook")
	}
	return shared[index], nil
}

func nistWorkbookXML(workbook *zip.Reader, name string) (*xmlElement, error) {
	// ZipFile.read uses the final member when a ZIP repeats a filename.
	var selected *zip.File
	for _, file := range workbook.File {
		if file.Name == name {
			selected = file
		}
	}
	if selected == nil {
		return nil, policyInputError("NIST workbook is missing " + name)
	}
	if selected.Flags&1 != 0 {
		return nil, policyInputError("NIST workbook member is encrypted")
	}
	file, err := selected.Open()
	if err != nil {
		return nil, policyInputError("NIST workbook member could not be opened")
	}
	defer func() { _ = file.Close() }()
	// The reviewed reference puts no expanded member ceiling on these two files.
	data, err := io.ReadAll(file)
	if err != nil {
		return nil, policyInputError("NIST workbook member could not be read")
	}
	return parsePolicyXML(data)
}

func nistFunctionTitle(text string) string {
	var out strings.Builder
	previousCased := false
	for _, r := range text {
		cased := unicode.ToLower(r) != unicode.ToUpper(r)
		if previousCased {
			out.WriteRune(unicode.ToLower(r))
		} else {
			out.WriteRune(unicode.ToTitle(r))
		}
		previousCased = cased
	}
	return out.String()
}
