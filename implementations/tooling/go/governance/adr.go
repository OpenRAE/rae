package governance

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"io/fs"
	"os/exec"
	"path"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"unicode"
)

const adrDirectory = "docs/decisions/adrs"
const adrManifest = adrDirectory + "/adr-index.yaml"

type adrPin struct {
	id, path, pin string
	refs          []string
}

type adrDocument struct{ id, path, text string }

func amendmentBounds(text string) (int, int, bool) {
	inFence, found := false, false
	start, offset := 0, 0
	for _, line := range pythonLines(text, true) {
		current := offset
		offset += len(line)
		if strings.HasPrefix(strings.TrimLeftFunc(line, pythonWhitespace), "```") {
			inFence = !inFence
			continue
		}
		if inFence {
			continue
		}
		body := strings.TrimRight(line, "\n")
		if !found {
			if regexp.MustCompile(`^##` + pythonSpace() + `+Amendments` + pythonSpace() + `*$`).MatchString(body) {
				start, found = current, true
			}
		} else if regexp.MustCompile(`^##` + pythonSpace() + `+`).MatchString(body) {
			return start, current, true
		}
	}
	return start, len(text), found
}

func adrHash(text string) string {
	if start, end, found := amendmentBounds(text); found {
		text = text[:start] + text[end:]
	}
	lines := pythonLines(text, false)
	for i, line := range lines {
		lines[i] = strings.TrimRightFunc(line, pythonWhitespace)
	}
	canonical := strings.TrimRight(strings.Join(lines, "\n"), "\n") + "\n"
	return fmt.Sprintf("%x", sha256.Sum256([]byte(canonical)))
}

func amendmentRefs(text string) []string {
	refs := []string{}
	start, end, found := amendmentBounds(text)
	if !found {
		return refs
	}
	for _, line := range pythonLines(text[start:end], false) {
		line = strings.TrimFunc(line, pythonWhitespace)
		if !strings.HasPrefix(line, "|") {
			continue
		}
		cells := strings.Split(strings.Trim(line, "|"), "|")
		if len(cells) < 3 {
			continue
		}
		for i, cell := range cells {
			cells[i] = strings.TrimFunc(cell, pythonWhitespace)
		}
		if strings.EqualFold(cells[0], "date") || strings.Trim(strings.Join(cells, ""), "-: ") == "" {
			continue
		}
		refs = append(refs, cells[1])
	}
	return refs
}

func markdownSection(text, section string) (string, bool) {
	marker := "## " + section
	if _, after, ok := strings.Cut(text, marker); ok {
		body := strings.TrimLeftFunc(after, pythonWhitespace)
		if end := strings.Index(body, "\n## "); end >= 0 {
			body = body[:end]
		}
		lines := pythonLines(strings.TrimFunc(body, pythonWhitespace), false)
		if len(lines) == 0 {
			return "", false
		}
		return strings.TrimFunc(lines[0], pythonWhitespace), true
	}
	match := regexp.MustCompile(`(?m)^\*\*` + regexp.QuoteMeta(section) + `:\*\*` + pythonSpace() + `*(.+)$`).FindStringSubmatch(text)
	if match == nil {
		return "", false
	}
	return strings.TrimFunc(match[1], pythonWhitespace), true
}

func acceptedADRs(r *repository) ([]adrDocument, error) {
	names, err := fs.Glob(r.root.FS(), adrDirectory+"/adr-*.md")
	if err != nil {
		return nil, err
	}
	documents := []adrDocument{}
	positions := map[string]int{}
	for _, name := range names {
		text, err := r.text(name)
		if err != nil {
			if errors.Is(err, errNotUTF8) {
				continue
			}
			return nil, err
		}
		header := regexp.MustCompile(`(?m)^# ADR-(\p{Nd}{3}): (.+)$`).FindStringSubmatch(text)
		status, statusOK := markdownSection(text, "Status")
		_, dateOK := markdownSection(text, "Date")
		if header == nil || !statusOK || !dateOK || !strings.EqualFold(strings.Join(strings.Fields(status), " "), "accepted") {
			continue
		}
		resolved, err := r.resolve(name)
		if err != nil {
			return nil, err
		}
		doc := adrDocument{id: "ADR-" + header[1], path: resolved, text: text}
		if i, exists := positions[doc.id]; exists {
			documents[i] = doc
		} else {
			positions[doc.id] = len(documents)
			documents = append(documents, doc)
		}
	}
	return documents, nil
}

func (c *checker) adr(ctx context.Context, r *repository) (Report, error) {
	pins, findings := readADRPins(r)
	if pins == nil {
		return finish(findings), nil
	}
	for _, pin := range pins {
		if !r.safe(pin.path) {
			findings = append(findings, finding("adr-manifest-path-unsafe", pin.id+": path escapes the repository", pin.path))
		}
	}
	if len(findings) > 0 {
		return finish(findings), nil
	}
	documents, err := acceptedADRs(r)
	if err != nil {
		return Report{}, err
	}
	findings = checkADRPins(r, pins, documents)
	if len(findings) == 0 && (c.request.BaseRevision != "" || c.request.Staged) {
		findings, err = c.adrEdits(ctx, r, documents)
	}
	return finish(findings), err
}

func gitOptional(ctx context.Context, r *repository, input string, args ...string) ([]byte, error) {
	data, err := r.git(ctx, input, args...)
	if _, ok := errors.AsType[*exec.ExitError](err); ok {
		return nil, nil
	}
	return data, err
}

func gitBlob(ctx context.Context, r *repository, ref string, follow bool) ([]byte, error) {
	if !regexp.MustCompile(`^(?:[A-Za-z0-9_][A-Za-z0-9_./@^~{}-]*(?::[A-Za-z0-9_./-]+)?|:[A-Za-z0-9_./-]+)$`).MatchString(ref) {
		return nil, errors.New("a git revision must not start with '-' or contain other characters")
	}
	if !follow {
		return gitOptional(ctx, r, "", "show", "--end-of-options", ref)
	}
	data, err := gitOptional(ctx, r, ref+"\n", "cat-file", "--batch", "--follow-symlinks")
	if err != nil || data == nil {
		return nil, err
	}
	header, payload, ok := strings.Cut(string(data), "\n")
	fields := strings.Fields(header)
	if !ok || len(fields) != 3 || fields[1] != "blob" {
		return nil, nil
	}
	size, err := strconv.Atoi(fields[2])
	if err != nil || size < 0 || size > len(payload) {
		return nil, errors.New("invalid Git blob response")
	}
	return []byte(payload[:size]), nil
}

func adrBasePaths(ctx context.Context, r *repository, base string) (map[string]string, error) {
	paths := map[string]string{}
	data, err := gitBlob(ctx, r, base+":"+adrManifest, true)
	if err != nil {
		return nil, err
	}
	raw, err := yamlValue(data, false)
	if err != nil {
		return paths, nil //nolint:nilerr // An unreadable historical manifest uses the current ADR path.
	}
	m, _ := raw.(*mapping)
	entries, _ := m.get("adrs").([]any)
	for _, value := range entries {
		entry, _ := value.(*mapping)
		id, idOK := entry.get("id").(string)
		name, nameOK := entry.get("path").(string)
		if idOK && nameOK {
			paths[id] = path.Clean(name)
		}
	}
	return paths, nil
}

func pythonWhitespace(r rune) bool { return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f }
func pythonSpace() string {
	return `[\t\n\v\f\r \x{1c}-\x{1f}\x{85}\x{a0}\x{1680}\x{2000}-\x{200a}\x{2028}\x{2029}\x{202f}\x{205f}\x{3000}]`
}

func pythonLines(text string, keepEnds bool) []string {
	lines := []string{}
	start := 0
	for i, r := range text {
		if r != '\n' && r != '\r' && r != '\v' && r != '\f' && r != 0x1c && r != 0x1d && r != 0x1e && r != 0x85 && r != 0x2028 && r != 0x2029 {
			continue
		}
		if i < start {
			continue
		}
		size := len(string(r))
		if r == '\r' && i+1 < len(text) && text[i+1] == '\n' {
			size++
		}
		end := i
		if keepEnds {
			end += size
		}
		lines = append(lines, text[start:end])
		start = i + size
	}
	if start < len(text) {
		lines = append(lines, text[start:])
	}
	return lines
}

func checkADRPins(r *repository, pins []adrPin, documents []adrDocument) []Finding {
	findings := []Finding{}
	byID := map[string]adrDocument{}
	pinned := map[string]bool{}
	for _, pin := range pins {
		pinned[pin.id] = true
	}
	for _, doc := range documents {
		byID[doc.id] = doc
		if !pinned[doc.id] {
			findings = append(findings, finding("adr-pin-missing", doc.id+" is accepted but not pinned in the manifest", doc.path))
		}
	}
	for _, pin := range pins {
		if _, exists := byID[pin.id]; !exists {
			findings = append(findings, finding("adr-pin-orphan", "manifest pins "+pin.id+" but it is missing or not 'accepted' on disk", pin.path))
		}
	}
	for _, pin := range pins {
		if doc, exists := byID[pin.id]; exists {
			findings = append(findings, checkADRPin(r, pin, doc)...)
		}
	}
	return findings
}

func checkADRPin(r *repository, pin adrPin, doc adrDocument) []Finding {
	findings := []Finding{}
	left, leftErr := r.resolve(pin.path)
	right, rightErr := r.resolve(doc.path)
	if leftErr != nil || rightErr != nil || left != right {
		return []Finding{finding("adr-manifest-malformed", pin.id+": manifest path does not resolve to the ADR file on disk", pin.path)}
	}
	if adrHash(doc.text) != pin.pin {
		findings = append(findings, finding("adr-pin-stale", pin.id+" content differs from its pinned hash; record an amendment (and update the pin) or supersede it with a new ADR", pin.path))
	}
	actual, expected := amendmentRefs(doc.text), append([]string{}, pin.refs...)
	slices.Sort(actual)
	slices.Sort(expected)
	if !slices.Equal(actual, expected) {
		findings = append(findings, finding("adr-amendment-record-mismatch", pin.id+": manifest amendment refs "+pythonRepr(expected)+" do not match the ADR ## Amendments rows "+pythonRepr(actual), pin.path))
	}
	return findings
}
