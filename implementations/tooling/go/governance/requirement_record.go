package governance

import (
	"io"
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"
)

const requirementArchived = "ARCHIVED"
const requirementDeprecated = "DEPRECATED"

const requirementLimit = 512 * 1024
const requirementReadFailure = "Requirement authority cannot be read and validated."

type requirementError string

func (e requirementError) Error() string { return string(e) }

type requirementLink struct{ kind, artifact, identifier string }
type requirementRecord struct {
	uid, status string
	links       []requirementLink
}
type requirementReader struct {
	repo    *repository
	records map[string]requirementRecord
}

func canonicalUID(uid string) bool {
	return regexp.MustCompile(`^[A-Z]{3}-\p{Nd}{3,}$`).MatchString(uid)
}

func (c *requirementReader) load(uid string) (requirementRecord, error) {
	if !canonicalUID(uid) {
		return requirementRecord{}, requirementError("Requirement identity is not a canonical UID.")
	}
	if record, exists := c.records[uid]; exists {
		record.links = slices.Clone(record.links)
		return record, nil
	}
	name := "docs/requirements/" + uid + "/requirement.md"
	data, err := c.read(name)
	if err != nil {
		return requirementRecord{}, err
	}
	frontmatter, body, err := requirementParts(string(data))
	if err != nil {
		return requirementRecord{}, err
	}
	metadata, err := requirementMetadata(frontmatter)
	if err != nil {
		return requirementRecord{}, err
	}
	record, err := admitRequirement(metadata, uid)
	if err != nil {
		return requirementRecord{}, err
	}
	record.links, err = requirementTraceability(body)
	if err != nil {
		return requirementRecord{}, err
	}
	if c.records == nil {
		c.records = map[string]requirementRecord{}
	}
	c.records[uid] = record
	record.links = slices.Clone(record.links)
	return record, nil
}

func (c *requirementReader) read(name string) ([]byte, error) {
	resolved, err := c.repo.resolve(name)
	if err != nil || resolved != name {
		return nil, requirementError("Requirement source is not its bounded canonical file.")
	}
	info, err := c.repo.root.Stat(name)
	if err != nil {
		return nil, requirementError(requirementReadFailure)
	}
	if info.Size() > requirementLimit {
		return nil, requirementError("Requirement source is not its bounded canonical file.")
	}
	source, err := c.repo.root.Open(name)
	if err != nil {
		return nil, requirementError(requirementReadFailure)
	}
	defer func() { _ = source.Close() }()
	data, err := io.ReadAll(io.LimitReader(source, requirementLimit+1))
	if err != nil || !utf8.Valid(data) {
		return nil, requirementError(requirementReadFailure)
	}
	if len(data) > requirementLimit {
		return nil, requirementError("Requirement source exceeds its bounded file size.")
	}
	return data, nil
}

func requirementParts(document string) (string, string, error) {
	lines := pythonLines(document, false)
	if len(lines) == 0 || lines[0] != "---" {
		return "", "", requirementError("Requirement source has no YAML frontmatter.")
	}
	end := slices.Index(lines[1:], "---")
	if end < 0 {
		return "", "", requirementError("Requirement frontmatter is not terminated.")
	}
	end++
	return strings.Join(lines[1:end], "\n"), strings.Join(lines[end+1:], "\n"), nil
}

func requirementMetadata(frontmatter string) (any, error) {
	node, err := yamlDocument([]byte(frontmatter))
	if err != nil || !boundedRequirementNode(node, 0) {
		return nil, requirementError(requirementReadFailure)
	}
	value, err := constructYAML(node, map[*yaml.Node]any{}, 0)
	if err != nil {
		return nil, requirementError(requirementReadFailure)
	}
	return value, nil
}

func boundedRequirementNode(node *yaml.Node, depth int) bool {
	if node.Kind == yaml.AliasNode {
		return false
	}
	if node.Kind == yaml.MappingNode || node.Kind == yaml.SequenceNode {
		depth++
	}
	if depth > 64 {
		return false
	}
	if node.Kind == yaml.MappingNode && !uniqueScalarKeys(node) {
		return false
	}
	for _, child := range node.Content {
		if !boundedRequirementNode(child, depth) {
			return false
		}
	}
	return true
}

func uniqueScalarKeys(node *yaml.Node) bool {
	seen := map[string]bool{}
	for i := 0; i < len(node.Content); i += 2 {
		key := node.Content[i]
		if key.Kind != yaml.ScalarNode || seen[key.Value] {
			return false
		}
		seen[key.Value] = true
	}
	return true
}

func admitRequirement(value any, uid string) (requirementRecord, error) {
	m, ok := value.(*mapping)
	if !ok || m.get("id") != uid {
		return requirementRecord{}, requirementError("Requirement metadata does not match its canonical identity.")
	}
	status, ok := m.get("status").(string)
	if !ok || !slices.Contains([]string{"DRAFT", "ACTIVE", requirementDeprecated, requirementArchived}, status) {
		return requirementRecord{}, requirementError("Requirement metadata has no valid governed status.")
	}
	return requirementRecord{uid: uid, status: status}, nil
}

func requirementTraceability(body string) ([]requirementLink, error) {
	links := []requirementLink{}
	inSection := false
	pattern := regexp.MustCompile("^- ([A-Z][A-Z_]*) → ([A-Z][A-Z_]*) `([^`\\n]+)`(?: \\([^\\n]*\\))?$")
	for _, line := range pythonLines(body, false) {
		if strings.HasPrefix(line, "## ") {
			inSection = line == "## Traceability"
		}
		if !inSection || !strings.HasPrefix(line, "- ") {
			continue
		}
		match := pattern.FindStringSubmatch(line)
		if match == nil {
			return nil, requirementError("Requirement traceability contains an invalid link record.")
		}
		links = append(links, requirementLink{kind: match[1], artifact: match[2], identifier: match[3]})
	}
	return links, nil
}
