package arch

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io/fs"
	"maps"
	"path"
	"slices"
	"strings"
)

func contentDigest(content []byte) string {
	sum := sha256.Sum256(content)
	return hex.EncodeToString(sum[:])
}

func apiCommitment(pkg Package) string {
	content, err := json.Marshal(pkg.API)
	if err != nil {
		panic(err)
	} // The closed map/string/slice shape is always JSON-encodable.
	return "<!-- go-api " + pkg.Dir + " " + contentDigest(content) + " -->"
}

// CheckDocuments checks reviewed API commitments and the current system view.
// The caller supplies a repository-contained filesystem (os.Root.FS in the command).
func (m *Model) CheckDocuments(repo fs.FS) ([]Finding, error) {
	var findings []Finding
	report := func(rule, location, problem, fix string) {
		findings = append(findings, Finding{Rule: rule, Location: location, Problem: problem, Fix: fix})
	}
	for _, pkg := range m.Packages {
		if !documentPath(pkg.Design) {
			report(ruleAPI, pkg.Dir, "the package has no safe owning design.", "set design to a repository documentation file.")
			continue
		}
		content, err := fs.ReadFile(repo, pkg.Design)
		if err != nil {
			return nil, fmt.Errorf("read design %s: %w", pkg.Design, err)
		}
		if !strings.Contains(string(content), apiCommitment(pkg)) {
			report(ruleAPI, pkg.Design, "the design does not commit to the intended API of "+pkg.Dir+".", "review the API snapshot, then record "+apiCommitment(pkg)+" in its owning design.")
		}
	}
	if !documentPath(m.Overview) {
		report(ruleViews, m.Overview, "the model needs a current overview.", "set overview to the current system design file.")
		return findings, nil
	}
	content, err := fs.ReadFile(repo, m.Overview)
	if err != nil {
		return nil, err
	}
	for _, layer := range m.Layers {
		if !strings.Contains(string(content), m.componentCommitment(layer)) {
			report(ruleViews, m.Overview, "the authored trust view has a stale component binding for "+layer.Name+".", "review its data flows and source evidence, then update the go-component commitment from archcheck -view.")
		}
	}
	view := m.View()
	if strings.Count(string(content), "<!-- go-view -->") != 1 || !strings.Contains(string(content), view) {
		report(ruleViews, m.Overview, "the generated component and dependency view is stale.", "review and replace the go-view block with archcheck -view output.")
	}
	evidence, err := m.checkViewEvidence(repo)
	return slices.Concat(findings, evidence), err
}

func (m *Model) checkViewEvidence(repo fs.FS) ([]Finding, error) {
	var findings []Finding
	report := func(rule, location, problem, fix string) {
		findings = append(findings, Finding{Rule: rule, Location: location, Problem: problem, Fix: fix})
	}

	if len(m.Sources) == 0 {
		report(ruleViews, m.Overview, "the trust view has no bound evidence.", "bind its contracts, ADRs and threat/control sources by SHA-256.")
	}
	for _, name := range slices.Sorted(maps.Keys(m.Sources)) {
		if !documentPath(name) && (!isRepoDir(name) || (!within(name, "contracts") && !within(name, "specs"))) {
			report(ruleViews, name, "the evidence path is outside approved design surfaces.", "use a clean documentation, contract or specification file.")
			continue
		}
		source, err := fs.ReadFile(repo, name)
		if err != nil {
			return nil, err
		}
		if contentDigest(source) != m.Sources[name] {
			report(ruleViews, name, "the authored trust view has stale evidence.", "review the trust view against the source, then update its source digest and generated view.")
		}
	}
	return findings, nil
}

func documentPath(name string) bool {
	return isRepoDir(name) && within(name, "docs") && path.Ext(name) == ".md"
}

// View renders the mechanical component view, including planned layers and
// actual package edges. It returns text; it never overwrites reviewed documents.
func (m *Model) View() string {
	var out strings.Builder
	out.WriteString("<!-- go-view -->\n\n| Layer | Status | Allowed dependencies |\n| --- | --- | --- |\n")
	for _, layer := range m.Layers {
		status := "planned"
		for _, pkg := range m.Packages {
			if pkg.Layer == layer.Name {
				status = "implemented packages"
				break
			}
		}
		fmt.Fprintf(&out, "| `%s` | %s | %s |\n", layer.Name, status, strings.Join(layer.Uses, ", "))
	}
	out.WriteString("\n```mermaid\nflowchart BT\n")
	for i, layer := range m.Layers {
		fmt.Fprintf(&out, "    L%d[%q]\n", i, layer.Name)
		for _, dep := range layer.Uses {
			j := slices.IndexFunc(m.Layers, func(l Layer) bool { return l.Name == dep })
			fmt.Fprintf(&out, "    L%d --> L%d\n", i, j)
		}
	}
	out.WriteString("```\n\n| Package owner | Layer | Cross-layer visibility | Consumer importable | Actual dependencies |\n| --- | --- | --- | --- | --- |\n")
	for _, pkg := range m.Packages {
		consumer := !strings.Contains("/"+pkg.Dir+"/", "/internal/") && !strings.Contains(pkg.Dir, "/cmd/")
		fmt.Fprintf(&out, "| `%s` | %s | %t | %t | %s |\n", pkg.Dir, pkg.Layer, pkg.Public, consumer, strings.Join(pkg.Imports, ", "))
	}
	m.consumerView(&out)
	out.WriteString("\n| Trust-view evidence | SHA-256 |\n| --- | --- |\n")
	for _, name := range slices.Sorted(maps.Keys(m.Sources)) {
		fmt.Fprintf(&out, "| `%s` | `%s` |\n", name, m.Sources[name])
	}
	for _, layer := range m.Layers {
		fmt.Fprintln(&out, m.componentCommitment(layer))
	}
	out.WriteString("\n<!-- /go-view -->\n")
	return out.String()
}

func (m *Model) consumerView(out *strings.Builder) {
	a := m.ConsumerAPI
	if a == nil {
		return
	}
	modules := map[string]string{}
	out.WriteString("\n| Consumer repository owner | Module |\n| --- | --- |\n")
	for _, module := range a.Modules {
		prefix := module.Module
		if prefix == "" {
			prefix = "RUNTIME"
		}
		modules[module.Owner] = prefix
		status := "`" + prefix + "`"
		if module.Module == "" {
			status += " (approval pending #1893)"
		}
		fmt.Fprintf(out, "| %s | %s |\n", module.Owner, status)
	}
	out.WriteString("\n| Planned public package | Owner | Operations / types | Public dependencies | Consumers | Delivery issues |\n| --- | --- | --- | --- | --- | --- |\n")
	for _, p := range a.Packages {
		issues := make([]string, 0, len(p.Issues))
		for _, issue := range p.Issues {
			issues = append(issues, fmt.Sprintf("#%d", issue))
		}
		fmt.Fprintf(out, "| `%s/%s` | %s | %s | %s | %s | %s |\n", modules[p.Owner], p.Path, p.Owner, strings.Join(p.Symbols, ", "), strings.Join(p.Uses, ", "), strings.Join(p.Consumers, ", "), strings.Join(issues, ", "))
	}
	out.WriteString("\n| Executable | Publisher | Entry point | Public composition dependencies |\n| --- | --- | --- | --- |\n")
	for _, command := range a.Commands {
		fmt.Fprintf(out, "| `%s` | %s | `%s/%s` | %s |\n", command.Name, command.Owner, modules[command.Owner], command.EntryPoint, strings.Join(command.Uses, ", "))
	}
	content, err := json.Marshal(a)
	if err != nil {
		panic(err) // The closed string, slice and integer model is JSON-encodable.
	}
	fmt.Fprintln(out, "\n<!-- go-consumer "+contentDigest(content)+" -->")
}

func (m *Model) componentCommitment(layer Layer) string {
	packages := []Package{}
	for _, pkg := range m.Packages {
		if pkg.Layer == layer.Name {
			packages = append(packages, pkg)
		}
	}
	content, err := json.Marshal(struct {
		Layer    Layer             `json:"layer"`
		Packages []Package         `json:"packages"`
		Sources  map[string]string `json:"sources"`
	}{layer, packages, m.Sources})
	if err != nil {
		panic(err)
	}
	return "<!-- go-component " + layer.Name + " " + contentDigest(content) + " -->"
}
