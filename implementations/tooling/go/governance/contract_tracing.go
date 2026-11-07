package governance

import (
	"errors"
	"io/fs"
	"path"
	"path/filepath"
	"slices"
	"strings"
)

func publishedSchemas(r *repository) ([]string, error) {
	names := []string{}
	resolved, err := r.resolve("contracts/schemas")
	if err != nil {
		return nil, err
	}
	info, err := r.root.Stat(resolved)
	if errors.Is(err, fs.ErrNotExist) {
		return names, nil
	}
	if err != nil {
		return nil, err
	}
	if !info.IsDir() {
		return names, nil
	}
	return publishedSchemaEntries(r, resolved)
}

func publishedSchemaEntries(r *repository, resolved string) ([]string, error) {
	names := []string{}
	err := fs.WalkDir(r.root.FS(), resolved, func(name string, entry fs.DirEntry, err error) error {
		if secretPath(name) {
			return errUnsafePath
		}
		if errors.Is(err, fs.ErrNotExist) {
			return nil
		}
		if err != nil {
			return err
		}
		if name != resolved && strings.HasSuffix(entry.Name(), ".json") {
			relative, err := filepath.Rel(resolved, name)
			if err != nil {
				return err
			}
			names = append(names, "contracts/schemas/"+filepath.ToSlash(relative))
		}
		return nil
	})
	slices.Sort(names)
	return names, err
}

func requirementUIDs(r *repository) ([]string, error) {
	resolved, resolveErr := r.resolve("docs/requirements")
	if resolveErr != nil {
		return nil, resolveErr
	}
	info, statErr := r.root.Stat(resolved)
	if statErr == nil && !info.IsDir() {
		return []string{}, nil
	}
	entries, err := fs.ReadDir(r.root.FS(), resolved)
	if errors.Is(err, fs.ErrNotExist) {
		return []string{}, nil
	}
	if err != nil {
		return nil, err
	}
	uids := []string{}
	for _, entry := range entries {
		name := "docs/requirements/" + entry.Name()
		if secretPath(name) {
			return nil, errUnsafePath
		}
		if requirementInventoryDirectory(r, name, entry) {
			uids = append(uids, entry.Name())
		}
	}
	return uids, nil
}

func governingOwners(r *repository) (map[string][]string, []Finding, error) {
	uids, err := requirementUIDs(r)
	if err != nil {
		return nil, nil, err
	}
	reader := requirementReader{repo: r}
	owners, findings := map[string][]string{}, []Finding{}
	for _, uid := range uids {
		record, err := reader.load(uid)
		if err != nil {
			findings = append(findings, finding("contract-requirement-record-unreadable", err.Error(), "docs/requirements/"+uid+"/requirement.md"))
			continue
		}
		if record.status == requirementArchived || record.status == requirementDeprecated {
			continue
		}
		addGoverningOwner(owners, uid, record.links)
	}
	return owners, findings, nil
}

func addGoverningOwner(owners map[string][]string, uid string, links []requirementLink) {
	for _, link := range links {
		if link.kind == "IMPLEMENTS" && link.artifact == "SPEC" && !slices.Contains(owners[link.identifier], uid) {
			owners[link.identifier] = append(owners[link.identifier], uid)
		}
	}
}

func contractTracing(r *repository, mode Mode) (Report, error) {
	owners, findings, err := governingOwners(r)
	if err != nil {
		return Report{}, err
	}
	schemas, err := publishedSchemas(r)
	if err != nil {
		return Report{}, err
	}
	if mode == Inventory {
		return Report{Text: tracingReport(schemas, owners, findings)}, nil
	}
	for _, name := range schemas {
		if len(owners[name]) == 0 {
			identifier := path.Base(name)
			if identifier != ".json" {
				identifier = strings.TrimSuffix(identifier, ".json")
			}
			findings = append(findings, finding("contract-requirement-trace-missing", "published contract "+identifier+" has no IMPLEMENTS → SPEC link from an ACTIVE or DRAFT requirement", name))
		}
	}
	return finish(findings), nil
}

func tracingReport(schemas []string, owners map[string][]string, findings []Finding) string {
	lines := []string{"Published-contract requirement tracing report (issue #712)", ""}
	for _, name := range schemas {
		list := slices.Clone(owners[name])
		slices.Sort(list)
		text := "UNTRACED"
		if len(list) > 0 {
			text = strings.Join(list, ", ")
		}
		lines = append(lines, "  - "+name+": "+text)
	}
	for _, f := range findings {
		lines = append(lines, "  - "+renderFinding(f))
	}
	return strings.Join(lines, "\n") + "\n"
}

// Preserve linked directory names in the inventory so the canonical record
// reader can emit its existing unreadable-record finding without following an
// unsafe link during discovery.
func requirementInventoryDirectory(r *repository, name string, entry fs.DirEntry) bool {
	canonical, err := r.resolve(name)
	if err != nil {
		return entry.Type()&fs.ModeSymlink != 0
	}
	info, err := r.root.Stat(canonical)
	if err != nil {
		return entry.Type()&fs.ModeSymlink != 0
	}
	return info.IsDir()
}
