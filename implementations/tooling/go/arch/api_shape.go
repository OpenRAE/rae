package arch

import "slices"

func (m *Model) checkAPIShape() []Finding {
	var findings []Finding
	ids := map[string]bool{}
	for _, config := range m.Configurations {
		if config.ID == "" || ids[config.ID] || config.GOOS == "" || config.GOARCH == "" {
			findings = append(findings, Finding{Rule: ruleAPI, Location: config.ID, Problem: "a build configuration needs a unique ID, GOOS and GOARCH.", Fix: "declare an explicit supported build context."})
		}
		ids[config.ID] = true
	}
	if len(ids) == 0 {
		findings = append(findings, Finding{Rule: ruleAPI, Location: "configurations", Problem: "no API build configuration is declared.", Fix: "declare supported GOOS, GOARCH and tags."})
	}
	for _, pkg := range m.Packages {
		if !documentPath(pkg.Design) || len(pkg.API) != len(ids) {
			findings = append(findings, Finding{Rule: ruleAPI, Location: pkg.Dir, Problem: "the package needs an owning design and an API snapshot for each build configuration.", Fix: "declare the design and intended API before writing code."})
		}
		for id, api := range pkg.API {
			if !ids[id] || api == nil || !slices.IsSorted(api) {
				findings = append(findings, Finding{Rule: ruleAPI, Location: pkg.Dir, Problem: "the API snapshot has an unknown configuration, null surface or unsorted declarations.", Fix: "use sorted typed declarations for each supported configuration."})
			}
		}
	}
	return findings
}
