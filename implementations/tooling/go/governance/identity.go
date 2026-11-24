package governance

import (
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"math/big"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"
)

const identityTrackedTree = "tracked-tree"

func identityCutover(ctx context.Context, r *repository) (Report, error) {
	records, findings := identityRecords(r)
	data, err := r.git(ctx, "", "ls-files", "-z")
	if cancelled := ctx.Err(); cancelled != nil {
		return Report{}, cancelled
	}
	if err != nil || !utf8.Valid(data) {
		findings = append(findings, identityFailure(identityTrackedTree, "cannot enumerate tracked files", ""))
		return finish(findings), nil //nolint:nilerr // Git discovery failures are explicit reference findings, not unavailable successful checks.
	}
	if len(findings) > 0 {
		return finish(findings), nil
	}
	tracked := strings.Split(strings.TrimSuffix(string(data), "\x00"), "\x00")
	if len(data) == 0 {
		tracked = nil
	}
	findings = append(findings, identityUntracked(records, tracked)...)
	for _, name := range tracked {
		if err := ctx.Err(); err != nil {
			return Report{}, err
		}
		findings = append(findings, identityFile(r, name, records)...)
	}
	return finish(findings), nil
}

func identityUntracked(records map[string]identityRecord, tracked []string) []Finding {
	findings := []Finding{}
	for _, group := range identityGroups() {
		missing := []string{}
		for name, record := range records {
			if record.category == group.category && !slices.Contains(tracked, name) {
				missing = append(missing, name)
			}
		}
		slices.Sort(missing)
		for _, name := range missing {
			findings = append(findings, identityFailure("manifest-path", group.label+" is not a tracked file", name))
		}
	}
	return findings
}

func identityFile(r *repository, name string, records map[string]identityRecord) []Finding {
	if !r.file(name) {
		return []Finding{identityFailure(identityTrackedTree, "tracked path is missing, unsafe, or not a regular file", name)}
	}
	content, err := r.read(name)
	if err != nil {
		return []Finding{identityFailure(identityTrackedTree, "tracked file cannot be read: "+err.Error(), name)}
	}
	if record, ok := records[name]; ok {
		return identityBoundContent(record, content)
	}
	if matches := identityMatches(string(content), true); len(matches) > 0 {
		return []Finding{identityFailure("live-token", fmt.Sprintf("contains %d retired identity occurrence(s) at line(s) %s", len(matches), identityLines(content, matches)), name)}
	}
	return nil
}

func identityBoundContent(record identityRecord, content []byte) []Finding {
	findings := []Finding{}
	var head []byte
	if record.suffix != nil {
		size := big.NewInt(int64(len(content)))
		if record.suffix.Cmp(size) > 0 {
			return []Finding{identityFailure("generated-content", fmt.Sprintf("generated history record is %d bytes, shorter than its classified suffix of %s bytes; the immutable tail was truncated", len(content), record.suffix), record.path)}
		}
		boundary := len(content) - int(record.suffix.Int64())
		head, content = content[:boundary], content[boundary:]
	}
	digest := fmt.Sprintf("%x", sha256.Sum256(content))
	if digest != record.digest {
		message := record.label + " content no longer matches its classified digest"
		if record.suffix != nil {
			message = "generated history record tail no longer matches its classified digest"
		}
		findings = append(findings, identityFailure(record.category+"-content", message, record.path))
	}
	count := len(identityMatches(string(content), true))
	if record.occurrences.Cmp(big.NewInt(int64(count))) != 0 {
		where := ""
		if record.suffix != nil {
			where = " in its classified tail"
		}
		findings = append(findings, identityFailure(record.category+"-count", fmt.Sprintf("%s declares %s occurrences%s but contains %d", record.label, record.occurrences, where, count), record.path))
	}
	if matches := identityMatches(string(head), true); len(matches) > 0 {
		findings = append(findings, identityFailure("generated-head", fmt.Sprintf("contains %d retired identity occurrence(s) outside the classified tail at line(s) %s; newly generated content carries no exemption", len(matches), identityLines(head, matches)), record.path))
	}
	return findings
}

func identityLines(content []byte, matches [][]int) string {
	lines := make([]string, 0, min(len(matches), 8))
	for _, match := range matches[:min(len(matches), 8)] {
		lines = append(lines, strconv.Itoa(bytes.Count(content[:match[0]], []byte{'\n'})+1))
	}
	result := strings.Join(lines, ", ")
	if len(matches) > 8 {
		result += fmt.Sprintf(", plus %d more", len(matches)-8)
	}
	return result
}

func identityMatches(text string, escaped bool) [][]int {
	matches := [][]int{}
	for offset := 0; offset+4 <= len(text); {
		if !identityStart(text, offset, escaped) {
			offset++
			continue
		}
		end := identityTokenEnd(text, offset+4)
		matches = append(matches, []int{offset, end})
		offset = end
	}
	return matches
}

func identityStart(text string, offset int, escaped bool) bool {
	switch text[offset : offset+4] {
	case "A" + "CES", "A" + "ces", "a" + "ces":
		return offset == 0 || !asciiAlphanumeric(text[offset-1]) || escaped && identityEscapeBoundary(text[:offset])
	default:
		return false
	}
}

func identityTokenEnd(text string, end int) int {
	for end < len(text) && strings.ContainsRune("-_.", rune(text[end])) {
		next := end + 1
		for next < len(text) && asciiAlphanumeric(text[next]) {
			next++
		}
		if next == end+1 {
			break
		}
		end = next
	}
	return end
}

func asciiAlphanumeric(c byte) bool {
	return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9'
}

func identityEscapeBoundary(prefix string) bool {
	for _, suffix := range []string{`\n`, `\r`, `\t`, `\x09`, `\x0a`, `\x0A`, `\x0d`, `\x0D`, `\u0009`, `\u000a`, `\u000A`, `\u000d`, `\u000D`} {
		if strings.HasSuffix(prefix, suffix) {
			return true
		}
	}
	return false
}
