package arch

import (
	"encoding/json"
	"go/token"
	"slices"
	"strings"

	"golang.org/x/mod/module"
)

const (
	consumerRAE        = "rae"
	consumerRuntime    = "runtime"
	consumerProductDir = "implementations/go"
)

func (m *Model) checkConsumerAPI() []Finding {
	a := m.ConsumerAPI
	if a == nil {
		if slices.ContainsFunc(m.Modules, func(v Module) bool { return v.Dir == consumerProductDir }) {
			return []Finding{{Rule: ruleConsumer, Location: "consumer_api", Problem: "consumer API: the product module requires its public consumer plan.", Fix: "restore the source-bound consumer_api declaration."}}
		}
		return nil // Models without a consumer plan retain their existing checks.
	}
	var findings []Finding
	report := func(location, problem string) {
		findings = append(findings, Finding{Rule: ruleConsumer, Location: location,
			Problem: "consumer API: " + problem, Fix: "correct the public owner, path or dependency in consumer_api and review its design."})
	}
	if !documentPath(a.Design) || m.Sources[a.Design] == "" {
		report(a.Design, "the consumer design needs a safe, source-bound documentation path.")
	}
	modules := m.checkConsumerModules(a, report)
	packages := m.checkConsumerPackages(a, modules, report)
	m.checkConsumerEdges(a.Packages, packages, report)
	graph := &Model{}
	for _, p := range a.Packages {
		graph.Packages = append(graph.Packages, Package{Dir: p.Owner + ":" + p.Path, Imports: p.Uses})
	}
	for _, f := range graph.checkPackageCycles() {
		report(f.Location, "consumer dependency cycle: "+f.Problem)
	}
	checkConsumerCommands(a.Commands, packages, report)
	return append(findings, m.checkConsumerImports(a)...)
}

// consumerLocation reports whether pkg implements a planned consumer package of
// its layer at that package's public path in the product module.
func (m *Model) consumerLocation(pkg Package) bool {
	return m.ConsumerAPI != nil && slices.ContainsFunc(m.ConsumerAPI.Packages, func(p ConsumerPackage) bool {
		return p.Layer == pkg.Layer && consumerProductDir+"/"+p.Path == pkg.Dir
	})
}

// boundary records the repository owner of each implemented package that
// crosses the split: consumer packages, command entrypoints and runtime code.
type boundary struct {
	model    *Model
	packages map[string]string // Implemented consumer package directory -> owner.
	roots    map[string]string // Consumer package or command entrypoint directory -> owner.
}

func (m *Model) boundary(a *ConsumerAPI) boundary {
	b := boundary{model: m, packages: map[string]string{}, roots: map[string]string{}}
	for _, p := range a.Packages {
		b.packages[consumerProductDir+"/"+p.Path] = p.Owner
		b.roots[consumerProductDir+"/"+p.Path] = p.Owner
	}
	for _, command := range a.Commands {
		b.roots[consumerProductDir+"/"+command.EntryPoint] = command.Owner
	}
	return b
}

// runtimeOwned reports whether dir is runtime code or a runtime entrypoint.
func (b boundary) runtimeOwned(dir string) bool {
	pkg, _ := b.model.pkg(dir)
	return pkg.Layer == consumerRuntime || b.roots[dir] == consumerRuntime
}

// problem describes why the package in from may not import dir across the
// repository boundary, with its fix, or returns "".
func (b boundary) problem(from, dir string) (problem, fix string) {
	if b.roots[from] == consumerRAE {
		if b.runtimeOwned(dir) {
			return "the RAE package imports runtime package " + dir + ".", "remove the reverse dependency; runtime imports RAE, never the opposite."
		}
		if reached := b.reachedRuntime(dir); reached != "" {
			return "the RAE package reaches runtime package " + reached + " through " + dir + ".", "remove the reverse dependency; runtime imports RAE, never the opposite."
		}
	}
	if b.runtimeOwned(from) && !b.runtimeOwned(dir) && b.packages[dir] != consumerRAE {
		return "runtime code imports " + dir + ", which is not an implemented public RAE consumer package.", "import the public RAE consumer package, or plan it in consumer_api first."
	}
	return "", ""
}

// reachedRuntime returns a runtime-owned package that dir imports directly or
// transitively in the model, or "".
func (b boundary) reachedRuntime(dir string) string {
	seen := map[string]bool{dir: true}
	queue := []string{dir}
	for len(queue) > 0 {
		pkg, _ := b.model.pkg(queue[0])
		queue = queue[1:]
		for _, dep := range pkg.Imports {
			if b.runtimeOwned(dep) {
				return dep
			}
			if !seen[dep] {
				seen[dep] = true
				queue = append(queue, dep)
			}
		}
	}
	return ""
}

// checkConsumerImports keeps the implemented packages and entrypoints on the
// repository boundary. A RAE package or entrypoint never reaches runtime code.
// Runtime code reaches the other layers only through implemented public RAE
// consumer packages, because Go rejects its internal imports after extraction.
func (m *Model) checkConsumerImports(a *ConsumerAPI) []Finding {
	b := m.boundary(a)
	var findings []Finding
	for _, pkg := range m.Packages {
		if b.packages[pkg.Dir] != "" && !pkg.Public {
			findings = append(findings, Finding{Rule: ruleConsumer, Location: pkg.Dir, Problem: "consumer API: an implemented consumer package must be public to other layers.", Fix: "set public for the package through the design step."})
		}
		for _, dep := range pkg.Imports {
			if problem, fix := b.problem(pkg.Dir, dep); problem != "" {
				findings = append(findings, Finding{Rule: ruleConsumer, Location: pkg.Dir, Problem: "consumer API: " + problem, Fix: fix})
			}
		}
	}
	return findings
}

// checkConsumerTestImports applies the repository boundary to the imports of
// test files, which move with their package at the extraction.
func (m *Model) checkConsumerTestImports(code Code) []Finding {
	if m.ConsumerAPI == nil {
		return nil
	}
	b := m.boundary(m.ConsumerAPI)
	var findings []Finding
	for _, pkg := range m.Packages {
		for _, dep := range code.Packages[pkg.Dir].Test {
			if problem, fix := b.problem(pkg.Dir, dep); problem != "" {
				findings = append(findings, Finding{Rule: ruleConsumer, Location: pkg.Dir, Problem: "consumer API: a test file: " + problem, Fix: fix})
			}
		}
	}
	return findings
}

func consumerPublicPath(name string) bool {
	if !isRepoDir(name) {
		return false
	}
	for segment := range strings.SplitSeq(name, "/") {
		if !token.IsIdentifier(segment) || segment == "internal" || segment == "cmd" {
			return false
		}
	}
	return true
}

func (m *Model) checkConsumerCommitment(p ConsumerPackage, report func(string, string)) {
	id := p.Owner + ":" + p.Path
	if p.Existing == "" && p.Declarations == "" {
		report(id, "a new consumer API needs exact Go declarations.")
	}
	if len(p.Symbols) == 0 || len(p.Issues) == 0 || len(p.Consumers) == 0 {
		report(id, "consumer packages need public identifiers, delivery issues and named consumers.")
	}
	checkConsumerSymbols(id, p.Symbols, report)
	for _, issue := range p.Issues {
		if issue <= 0 {
			report(id, "consumer delivery issues must be positive issue numbers.")
		}
	}
	for _, consumer := range p.Consumers {
		if !slices.Contains([]string{"environment-packs", "lilrae", "coldlight", consumerRuntime}, consumer) {
			report(id, "unknown consumer "+consumer+".")
		}
	}
	if p.Existing != "" {
		source, ok := m.pkg(p.Existing)
		if !ok || p.Owner != consumerRAE || !slices.Contains(p.Issues, 1892) || p.Existing != consumerProductDir+"/"+p.Path || source.Layer != p.Layer || p.ExistingAPISHA256 != consumerAPIDigest(source) {
			report(id, "a consumer relocation must name the RAE package at its public path, its current API digest and delivery issue 1892.")
		}
	}
}

func checkConsumerCommands(commands []ConsumerCommand, packages map[string]ConsumerPackage, report func(string, string)) {
	publishers := map[string]string{"raes": consumerRuntime, "raes-mcp": consumerRAE}
	seen := map[string]bool{}
	for _, command := range commands {
		if seen[command.Name] || publishers[command.Name] != command.Owner || command.Owner == "" || command.EntryPoint != "cmd/"+command.Name {
			report(command.Name, "each consumer executable needs its decided publisher and cmd entrypoint exactly once.")
		}
		seen[command.Name] = true
		if len(command.Uses) == 0 {
			report(command.Name, "the consumer command must name its public composition dependencies.")
		}
		checkConsumerCommandImports(command, packages, report)
	}
	for _, name := range []string{"raes", "raes-mcp"} {
		if !seen[name] {
			report(name, "consumer executable "+name+" needs one publisher.")
		}
	}
}

func (m *Model) checkConsumerModules(a *ConsumerAPI, report func(string, string)) map[string]ConsumerModule {
	modules := map[string]ConsumerModule{}
	for _, module := range a.Modules {
		_, duplicate := modules[module.Owner]
		if duplicate || !slices.Contains([]string{consumerRAE, consumerRuntime}, module.Owner) {
			report(module.Owner, "each consumer module needs one decided repository owner.")
		}
		modules[module.Owner] = module
		if problem := m.consumerModuleProblem(module); problem != "" {
			report(module.Owner, problem)
		}
	}
	if len(modules) != 2 || modules[consumerRAE].Owner == "" || modules[consumerRuntime].Owner == "" {
		report("modules", "declare the RAE and runtime consumer owners exactly once.")
	}
	return modules
}

func consumerModulePrefix(moduleName, repository string) bool {
	if invalidConsumerModulePath(moduleName) {
		return false
	}
	prefix := "github.com/" + repository
	return moduleName == prefix || strings.HasPrefix(moduleName, prefix+"/")
}

func invalidConsumerModulePath(name string) bool {
	return module.CheckPath(name) != nil || strings.Contains("/"+name+"/", "/internal/")
}

func consumerAPIDigest(pkg Package) string {
	content, err := json.Marshal(pkg.API)
	if err != nil {
		panic(err)
	}
	return contentDigest(content)
}

func (m *Model) checkConsumerPackages(a *ConsumerAPI, modules map[string]ConsumerModule, report func(string, string)) map[string]ConsumerPackage {
	packages := map[string]ConsumerPackage{}
	for _, p := range a.Packages {
		id := p.Owner + ":" + p.Path
		if _, duplicate := packages[id]; duplicate {
			report(id, "duplicate consumer package.")
		}
		packages[id] = p
		if _, ok := modules[p.Owner]; !ok || !consumerPublicPath(p.Path) || m.layer(p.Layer).Name == "" {
			report(id, "a consumer package needs a declared owner, layer and public Go path without internal or cmd.")
		}
		if (p.Owner == consumerRuntime) != (p.Layer == consumerRuntime) {
			report(id, "consumer execution packages belong to runtime; retained layers belong to RAE.")
		}
		m.checkConsumerCommitment(p, report)
	}
	return packages
}

func (m *Model) checkConsumerEdges(planned []ConsumerPackage, packages map[string]ConsumerPackage, report func(string, string)) {
	for _, p := range planned {
		id := p.Owner + ":" + p.Path
		for _, dep := range p.Uses {
			target, ok := packages[dep]
			if !ok || dep == id || (p.Owner == consumerRAE && target.Owner != consumerRAE) {
				report(id, "consumer dependency "+dep+" is unresolved, self-referential or reverses runtime-to-RAE ownership.")
				continue
			}
			if p.Layer != target.Layer && !slices.Contains(m.layer(p.Layer).Uses, target.Layer) {
				report(id, "consumer dependency "+dep+" violates the layer direction.")
			}
		}
	}
}

func checkConsumerSymbols(id string, symbols []string, report func(string, string)) {
	seen := map[string]bool{}
	for _, symbol := range symbols {
		if seen[symbol] {
			report(id, "duplicate consumer public identifier.")
		}
		seen[symbol] = true
		parts := strings.Split(symbol, ".")
		if len(parts) > 2 {
			report(id, "a consumer identifier must name an exported object or method.")
		}
		for _, part := range parts {
			if !token.IsIdentifier(part) || !token.IsExported(part) {
				report(id, "a consumer identifier must be exported.")
			}
		}
	}
}

func (m *Model) consumerModuleProblem(module ConsumerModule) string {
	if module.Owner == consumerRAE {
		if module.Repository != "OpenRAE/rae" || !slices.ContainsFunc(m.Modules, func(v Module) bool { return v.Dir == consumerProductDir && v.Path == module.Module }) {
			return "the canonical consumer module must retain the existing RAE product module."
		}
	}
	if module.Owner == consumerRuntime {
		if module.Module == "" && module.Repository == "" {
			return ""
		}
		if module.Module == "" || module.Repository == "" || module.Repository == "OpenRAE/rae" || !consumerModulePrefix(module.Module, module.Repository) {
			return "the runtime consumer module needs its own repository or both fields pending approval."
		}
	}
	return ""
}

func checkConsumerCommandImports(command ConsumerCommand, packages map[string]ConsumerPackage, report func(string, string)) {
	for _, dep := range command.Uses {
		target, ok := packages[dep]
		if !ok || (command.Owner == consumerRAE && target.Owner != consumerRAE) {
			report(command.Name, "consumer command dependency "+dep+" is unresolved or reverses repository ownership.")
		}
	}
}
