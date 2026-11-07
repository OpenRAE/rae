package governance

import (
	"io/fs"
	"path"
	"slices"
	"strconv"
	"strings"
)

func boundarySchemaBlock(block *mapping) []Finding {
	if block == nil {
		return []Finding{}
	}
	findings := []Finding{}
	for _, field := range []string{"normative_root", "publication_manifest", "forbidden_authority_roots", "forbidden_schema_filename_suffixes"} {
		if !block.has(field) {
			findings = append(findings, boundaryFailure("entry-field", "schema_authority is missing required field: "+field))
		}
	}
	for _, pair := range [][2]string{{"normative_root", "contracts/schemas/"}, {"publication_manifest", publicationManifest}} {
		field, expected := pair[0], pair[1]
		if !block.has(field) {
			continue
		}
		value := block.get(field)
		text, ok := value.(string)
		if !ok || text == "" {
			findings = append(findings, boundaryFailure(fieldTypeRule, "schema_authority."+field+" must be a non-empty string; got "+pythonRepr(value)))
		} else if text != expected {
			findings = append(findings, boundaryFailure("schema-authority-mismatch", "schema_authority."+field+" must equal "+pythonRepr(expected)+"; got "+pythonRepr(text)))
		}
	}
	findings = append(findings, boundaryForbiddenRoots(block)...)
	return append(findings, boundarySchemaSuffixes(block)...)
}

func boundaryForbiddenRoots(block *mapping) []Finding {
	values, ok := stringList(block.get("forbidden_authority_roots"), false)
	if !ok {
		if block.has("forbidden_authority_roots") {
			return []Finding{boundaryFailure(fieldTypeRule, "schema_authority.forbidden_authority_roots must be a list of strings")}
		}
		return []Finding{}
	}
	findings := []Finding{}
	for i, value := range values {
		if reason := boundaryPathShape(value, true); reason != "" {
			findings = append(findings, boundaryFailure("root-shape", "schema_authority.forbidden_authority_roots["+strconv.Itoa(i)+"] "+reason))
		}
	}
	if !slices.Contains(values, "implementations/") {
		findings = append(findings, boundaryFailure("schema-authority-forbidden-roots", "schema_authority.forbidden_authority_roots must include the baseline floor ['implementations/']; missing ['implementations/']"))
	}
	return findings
}

func boundarySchemaSuffixes(block *mapping) []Finding {
	suffixes, ok := stringList(block.get("forbidden_schema_filename_suffixes"), false)
	if !ok {
		if block.has("forbidden_schema_filename_suffixes") {
			return []Finding{boundaryFailure(fieldTypeRule, "schema_authority.forbidden_schema_filename_suffixes must be a list of strings")}
		}
		return []Finding{}
	}
	findings := []Finding{}
	if len(suffixes) == 0 {
		findings = append(findings, boundaryFailure(fieldTypeRule, "schema_authority.forbidden_schema_filename_suffixes must be a non-empty list"))
	}
	for i, suffix := range suffixes {
		if !strings.HasPrefix(suffix, ".") || len([]rune(suffix)) < 2 {
			findings = append(findings, boundaryFailure(fieldTypeRule, "schema_authority.forbidden_schema_filename_suffixes["+strconv.Itoa(i)+"] must be a non-empty extension starting with '.'; got "+pythonRepr(suffix)))
		}
	}
	return findings
}

func boundaryMisplacedSchemas(r *repository, block *mapping) []Finding {
	suffixes, _ := stringList(block.get("forbidden_schema_filename_suffixes"), false)
	roots, _ := stringList(block.get("forbidden_authority_roots"), false)
	findings := []Finding{}
	if len(suffixes) == 0 || len(roots) == 0 {
		return findings
	}
	for _, root := range roots {
		if boundaryPathShape(root, true) != "" {
			continue
		}
		findings = append(findings, boundarySchemaTree(r, root, suffixes)...)
	}
	return findings
}

func boundarySchemaTree(r *repository, root string, suffixes []string) []Finding {
	findings := []Finding{}
	pending := []string{strings.TrimSuffix(root, "/")}
	for len(pending) > 0 {
		directory := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		children, problems := boundarySchemaDirectory(r, directory, root, suffixes)
		findings = append(findings, problems...)
		for _, child := range slices.Backward(children) {
			pending = append(pending, child)
		}
	}
	return findings
}
func boundarySchemaDirectory(r *repository, directory, root string, suffixes []string) ([]string, []Finding) {
	findings := []Finding{}
	entries, err := boundaryDirectoryEntries(r, directory)
	if err != nil {
		return []string{}, []Finding{}
	} // os.walk suppresses unreadable subtrees.
	children := []string{}
	for _, entry := range entries {
		name := path.Join(directory, entry.Name())
		if entry.IsDir() {
			if !boundaryPruned(entry.Name()) {
				children = append(children, name)
			}
			continue
		}
		if boundaryLinkedDirectory(r, name, entry) {
			continue
		}
		if !strings.HasPrefix(name, "implementations/tooling/schemas/") && slices.ContainsFunc(suffixes, func(suffix string) bool { return strings.HasSuffix(entry.Name(), suffix) }) {
			findings = append(findings, finding("authority-boundary-schema-misplaced", "published schema file '"+name+"' is under a forbidden authority root ('"+root+"'); published schemas must live under 'contracts/schemas/'", name))
		}
	}
	return children, findings
}

func boundaryDirectoryEntries(r *repository, name string) ([]fs.DirEntry, error) {
	resolved, err := r.resolve(name)
	if err != nil {
		return nil, err
	}
	directory, err := r.root.Open(resolved)
	if err != nil {
		return nil, err
	}
	defer func() { _ = directory.Close() }()
	// os.walk retains directory entry order rather than sorting each directory.
	return directory.ReadDir(-1)
}

func boundaryLinkedDirectory(r *repository, name string, entry fs.DirEntry) bool {
	if entry.Type()&fs.ModeSymlink == 0 {
		return false
	}
	resolved, err := r.resolve(name)
	if err != nil {
		return false
	}
	info, err := r.root.Stat(resolved)
	return err == nil && info.IsDir()
}

func boundaryPruned(name string) bool {
	return strings.HasPrefix(name, ".") || slices.Contains([]string{"venv", "__pycache__", "node_modules", "build", "dist", "site-packages", "_build"}, name)
}
