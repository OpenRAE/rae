package module

import (
	"path"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func captureSources(files map[string][]byte, root string) (map[string][]byte, error) {
	options := source.DefaultOptions()
	options.RequireMapping = true
	budget, err := source.NewBudget(options.Limits)
	if err != nil {
		return nil, err
	}
	result := map[string][]byte{}
	pending := []string{root}
	for len(pending) > 0 {
		name := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if _, seen := result[name]; seen {
			continue
		}
		data, exists := files[name]
		if !exists {
			return nil, invalid()
		}
		document, err := source.Decode(data, options)
		if err != nil {
			return nil, err
		}
		if err = budget.AddDocument(document); err != nil {
			return nil, err
		}
		result[name] = slices.Clone(data)
		imports, err := capturedImports(document, name, budget)
		if err != nil {
			return nil, err
		}
		pending = append(pending, imports...)
	}
	return result, nil
}

func capturedImports(document *source.Document, name string, budget *source.Budget) ([]string, error) {
	payload := object(document.NormalizedValue())
	imports, exists := payload["imports"]
	if !exists {
		return []string{}, nil
	}
	rows, ok := imports.([]any)
	if !ok {
		return nil, invalid()
	}
	result := []string{}
	for _, row := range rows {
		if err := budget.AddImport(); err != nil {
			return nil, err
		}
		declaration := object(row)
		if declaration == nil {
			return nil, invalid()
		}
		reference := text(declaration["source"])
		if reference == "" {
			reference = "local:" + text(declaration["path"])
		}
		if after, local := strings.CutPrefix(reference, "local:"); local {
			target, err := capturedImportTarget(name, after)
			if err != nil {
				return nil, err
			}
			result = append(result, target)
		}
	}
	return result, nil
}
func capturedImportTarget(name, reference string) (string, error) {
	joined, err := source.ResolvePath(path.Join("verified", path.Dir(name)), reference)
	target, inside := strings.CutPrefix(joined, "verified/")
	if err != nil || !inside {
		return "", invalid()
	}
	return target, nil
}
