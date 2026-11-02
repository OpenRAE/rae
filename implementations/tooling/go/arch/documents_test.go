package arch

import (
	"strings"
	"testing"
	"testing/fstest"
)

func TestDocumentsBindAPIAndView(t *testing.T) {
	m := validModel()
	m.Overview = "docs/overview.md"
	m.Sources = map[string]string{"docs/evidence.md": contentDigest([]byte("evidence"))}
	repo := fstest.MapFS{"docs/evidence.md": {Data: []byte("evidence")}}
	for i := range m.Packages {
		p := &m.Packages[i]
		p.Design = "docs/design.md"
		p.API = map[string][]string{"linux": {}}
	}
	var design strings.Builder
	for _, p := range m.Packages {
		design.WriteString(apiCommitment(p) + "\n")
	}
	repo["docs/design.md"] = &fstest.MapFile{Data: []byte(design.String())}
	repo[m.Overview] = &fstest.MapFile{Data: []byte(m.View())}
	if got, err := m.CheckDocuments(repo); err != nil || len(got) > 0 {
		t.Fatalf("CheckDocuments() = %v, %v", got, err)
	}
	for _, name := range []string{"api", "design", "view", "source"} {
		t.Run(name, func(t *testing.T) {
			copyRepo := fstest.MapFS{}
			for k, v := range repo {
				copyRepo[k] = &fstest.MapFile{Data: append([]byte(nil), v.Data...)}
			}
			switch name {
			case "api":
				saved := m.Packages[0].API
				m.Packages[0].API = map[string][]string{"linux": {"func Changed()"}}
				copyRepo[m.Overview].Data = []byte(m.View())
				defer func() { m.Packages[0].API = saved }()
			case "design":
				delete(copyRepo, "docs/design.md")
			case "view":
				copyRepo[m.Overview].Data = []byte("stale")
			case "source":
				copyRepo["docs/evidence.md"].Data = []byte("changed")
			}
			got, err := m.CheckDocuments(copyRepo)
			if err == nil && len(got) == 0 {
				t.Error("CheckDocuments() accepted stale or missing design evidence")
			}
		})
	}
}
