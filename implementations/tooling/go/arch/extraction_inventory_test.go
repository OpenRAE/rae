package arch

import (
	"encoding/json"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

const extractionInventoryPath = "docs/decisions/issue-1891-runtime-extraction-inventory.json"

type extractionRule struct {
	OldPrefix      string  `json:"old_prefix"`
	NewPrefix      *string `json:"new_prefix"`
	Owner          string  `json:"owner"`
	Disposition    string  `json:"disposition"`
	PathCount      int     `json:"path_count"`
	ManifestSHA256 string  `json:"manifest_sha256"`
}

type extractionInventory struct {
	Source struct {
		Commit         string `json:"commit"`
		Tree           string `json:"tree"`
		PathCount      int    `json:"path_count"`
		ManifestSHA256 string `json:"manifest_sha256"`
	} `json:"source"`
	Rules          []extractionRule       `json:"rules"`
	Owners         map[string]string      `json:"owners"`
	Provenance     map[string]string      `json:"provenance"`
	ProductImports map[string][]string    `json:"product_imports"`
	Executables    []extractionExecutable `json:"executables"`
	Destination    struct {
		TransferAuthorized bool `json:"transfer_authorized"`
	} `json:"destination"`
	Release struct {
		GateIssue            int  `json:"gate_issue"`
		EarlierRuntimeLaunch bool `json:"earlier_runtime_launch"`
	} `json:"release"`
}

type extractionExecutable struct {
	Name                 string   `json:"name"`
	Publisher            string   `json:"publisher"`
	ImplementationOwners []string `json:"implementation_owners"`
}

func extractionRoot(t *testing.T) string {
	t.Helper()
	root, err := filepath.Abs("../../../..")
	if err != nil {
		t.Fatal(err)
	}
	return root
}

func extractionBytes(t *testing.T, name string) []byte {
	t.Helper()
	content, err := os.ReadFile(filepath.Join(extractionRoot(t), filepath.FromSlash(name)))
	if err != nil {
		t.Fatal(err)
	}
	return content
}

func loadExtractionInventory(t *testing.T) extractionInventory {
	t.Helper()
	var inventory extractionInventory
	if err := json.Unmarshal(extractionBytes(t, extractionInventoryPath), &inventory); err != nil {
		t.Fatal(err)
	}
	return inventory
}

func extractionGit(t *testing.T, args ...string) []byte {
	t.Helper()
	// Tests pass only read-only Git commands and pinned object/path operands, without a shell.
	if len(args) == 0 || !slices.Contains([]string{"ls-tree", "rev-parse"}, args[0]) {
		t.Fatal("extraction tests permit only object inventory reads")
	}
	command := exec.CommandContext(t.Context(), "git", args...) //nolint:gosec // G204: fixed Git program and read-only commands; no shell.
	command.Dir = extractionRoot(t)
	output, err := command.Output()
	if err != nil {
		t.Fatalf("git %v: %v", args, err)
	}
	return output
}

func extractionOwner(t *testing.T, rules []extractionRule, name string) extractionRule {
	t.Helper()
	var selected extractionRule
	for _, rule := range rules {
		if !within(name, rule.OldPrefix) || len(rule.OldPrefix) < len(selected.OldPrefix) {
			continue
		}
		if len(rule.OldPrefix) == len(selected.OldPrefix) {
			t.Fatalf("ambiguous owner for %s", name)
		}
		selected = rule
	}
	if selected.OldPrefix == "" {
		t.Fatalf("unowned path: %s", name)
	}
	return selected
}

func extractionRecords(t *testing.T, inventory extractionInventory) []string {
	t.Helper()
	raw := extractionGit(t, "ls-tree", "-r", "-z", "--full-tree", inventory.Source.Commit)
	if contentDigest(raw) != inventory.Source.ManifestSHA256 {
		t.Fatal("source inventory digest differs")
	}
	records := strings.Split(strings.TrimSuffix(string(raw), "\x00"), "\x00")
	if len(records) != inventory.Source.PathCount {
		t.Fatalf("source paths = %d, want %d", len(records), inventory.Source.PathCount)
	}
	return records
}

func extractionPath(t *testing.T, record string) string {
	t.Helper()
	_, name, ok := strings.Cut(record, "\t")
	if !ok {
		t.Fatal("source record has no path")
	}
	return name
}

func TestExtractionInventoryCoversEverySourceObjectOnce(t *testing.T) {
	inventory := loadExtractionInventory(t)
	if tree := strings.TrimSpace(string(extractionGit(t, "rev-parse", inventory.Source.Commit+"^{tree}"))); tree != inventory.Source.Tree {
		t.Fatalf("source tree = %s, want %s", tree, inventory.Source.Tree)
	}
	groups := map[string][]byte{}
	for _, record := range extractionRecords(t, inventory) {
		rule := extractionOwner(t, inventory.Rules, extractionPath(t, record))
		groups[rule.OldPrefix] = append(groups[rule.OldPrefix], []byte(record+"\x00")...)
	}
	seen := map[string]bool{}
	for _, rule := range inventory.Rules {
		if seen[rule.OldPrefix] {
			t.Fatalf("duplicate prefix: %s", rule.OldPrefix)
		}
		seen[rule.OldPrefix] = true
		group := groups[rule.OldPrefix]
		if len(group) == 0 || strings.Count(string(group), "\x00") != rule.PathCount || contentDigest(group) != rule.ManifestSHA256 {
			t.Fatalf("rule %s has unused paths or incorrect count/digest", rule.OldPrefix)
		}
	}
}

func TestExtractionDestinationsAreUnambiguous(t *testing.T) {
	inventory := loadExtractionInventory(t)
	destinations := map[string]bool{}
	for _, record := range extractionRecords(t, inventory) {
		name := extractionPath(t, record)
		rule := extractionOwner(t, inventory.Rules, name)
		if _, ok := inventory.Owners[rule.Owner]; !ok || !slices.Contains([]string{"retained", "moved", "consumed-by-version", "migration-only"}, rule.Disposition) {
			t.Fatalf("invalid owner or disposition for %s", name)
		}
		if rule.Disposition == "migration-only" {
			if rule.NewPrefix != nil {
				t.Fatalf("migration reference has a transfer destination: %s", name)
			}
			continue
		}
		if rule.NewPrefix == nil {
			t.Fatalf("missing destination: %s", name)
		}
		destination := *rule.NewPrefix + strings.TrimPrefix(name, rule.OldPrefix)
		identity := rule.Owner + ":" + destination
		if !isRepoDir(destination) || path.Clean(destination) != destination || destinations[identity] {
			t.Fatalf("unsafe or colliding destination: %s", identity)
		}
		destinations[identity] = true
	}
}

func TestExtractionProvenanceStaysWithItsAuthority(t *testing.T) {
	inventory := loadExtractionInventory(t)
	for name, oid := range inventory.Provenance {
		actual := strings.TrimSpace(string(extractionGit(t, "rev-parse", inventory.Source.Commit+":"+name)))
		if actual != oid || extractionOwner(t, inventory.Rules, name).Owner != "rae" {
			t.Fatalf("incorrect provenance or authority for %s", name)
		}
	}
}

func TestExtractionPreservesDependencyAndExecutableAuthority(t *testing.T) {
	inventory := loadExtractionInventory(t)
	if diff := cmp.Diff(map[string][]string{"rae": {}, "runtime": {"rae"}}, inventory.ProductImports); diff != "" {
		t.Fatalf("product imports (-want +got):\n%s", diff)
	}
	publishers := map[string]string{}
	for _, executable := range inventory.Executables {
		if _, exists := publishers[executable.Name]; exists {
			t.Fatalf("duplicate executable publisher: %s", executable.Name)
		}
		publishers[executable.Name] = executable.Publisher
		allowed := append([]string{executable.Publisher}, inventory.ProductImports[executable.Publisher]...)
		for _, owner := range executable.ImplementationOwners {
			if !slices.Contains(allowed, owner) {
				t.Fatalf("reverse dependency from %s to %s", executable.Name, owner)
			}
		}
	}
	if diff := cmp.Diff(map[string]string{"raes": "runtime", "raes-mcp": "rae"}, publishers); diff != "" {
		t.Fatalf("publishers (-want +got):\n%s", diff)
	}
	if inventory.Destination.TransferAuthorized || inventory.Release.GateIssue != 1804 || inventory.Release.EarlierRuntimeLaunch {
		t.Fatal("transfer approval or the common launch gate changed")
	}
}

func TestExtractionModelBindsInventoryEvidence(t *testing.T) {
	const decision = "docs/decisions/issue-1891-runtime-repository-boundary.md"
	var model Model
	if err := json.Unmarshal(extractionBytes(t, "implementations/architecture.json"), &model); err != nil {
		t.Fatal(err)
	}
	content := extractionBytes(t, decision)
	if model.Sources[decision] != contentDigest(content) {
		t.Fatal("model does not bind the split decision")
	}
	if !strings.Contains(string(content), "<!-- extraction-inventory "+contentDigest(extractionBytes(t, extractionInventoryPath))+" -->") {
		t.Fatal("decision does not bind the source inventory")
	}
}

func TestExtractionMixedResponsibilitiesKeepTheirSemanticOwner(t *testing.T) {
	inventory := loadExtractionInventory(t)
	cases := []struct{ name, owner, disposition string }{
		{"implementations/python/packages/raes/runtime_inventory.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_processor/trial_compiler/__init__.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_runtime/runtime_engine.py", "runtime", "migration-only"},
		{"implementations/python/packages/raes_operations/run_artifacts.py", "runtime", "migration-only"},
		{"implementations/python/packages/raes_conformance/conformance/fixture_suite.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_conformance/conformance/processor.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_conformance/conformance/report.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_conformance/conformance/modular_control_report.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_conformance/conformance/modular_control_types.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_conformance/conformance/mixed_backend_types.py", "rae", "migration-only"},
		{"implementations/python/packages/raes_conformance/conformance/target.py", "runtime", "migration-only"},
		{"contracts/schemas/experiment-core/materialization-archive-record-v1.json", "rae", "consumed-by-version"},
		{"docs/research/execution-architecture/evidence.json", "rae", "retained"},
		{"implementations/go/internal/base/clock/clock.go", "rae", "retained"},
		{"implementations/go/internal/parity/runner-inventory.json", "rae", "migration-only"},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			rule := extractionOwner(t, inventory.Rules, test.name)
			if rule.Owner != test.owner || rule.Disposition != test.disposition {
				t.Fatalf("owner/disposition = %s/%s, want %s/%s", rule.Owner, rule.Disposition, test.owner, test.disposition)
			}
		})
	}
}
