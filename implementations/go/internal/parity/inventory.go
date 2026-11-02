package parity

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io/fs"
	"slices"
)

type corpusInventory struct {
	Surfaces       map[string][]string `json:"surfaces"`
	Inputs         []string            `json:"inputs"`
	InputDigests   map[string]string   `json:"input_digests"`
	MissingInputs  []string            `json:"missing_inputs"`
	MissingSurface map[string][]string `json:"missing_surfaces"`
	Complete       bool                `json:"complete"`
	Regressions    struct {
		Complete         bool                `json:"complete"`
		TestCount        int                 `json:"test_count"`
		InputCount       int                 `json:"input_count"`
		NonProtocolTests []string            `json:"non_protocol_tests"`
		Origins          map[string][]string `json:"origins"`
		SourceIdentity   struct {
			TestTree        string `json:"test_tree"`
			CollectorSHA256 string `json:"collector_sha256"`
		} `json:"source_identity"`
	} `json:"regressions"`
}

// checkCorpusInventory verifies coverage against the actual loaded cases, even
// before Go runners exist. A manually asserted complete flag cannot hide gaps.
func checkCorpusInventory(fsys fs.FS, cases []Case) error {
	var inventory corpusInventory
	if err := decodeFile(fsys, "inventory.json", &inventory); err != nil {
		return err
	}
	if !inventory.Complete || len(inventory.MissingInputs) != 0 {
		return errors.New("corpus input inventory is incomplete")
	}
	keys, digests, names := inventoriedCases(cases)
	if err := checkSurfaceInventory(inventory, keys); err != nil {
		return err
	}
	if len(inventory.Inputs) == 0 || len(inventory.Inputs) != len(inventory.InputDigests) {
		return errors.New("corpus source input inventory is missing entries")
	}
	seen := map[string]bool{}
	for _, name := range inventory.Inputs {
		if seen[name] || !digests[inventory.InputDigests[name]] {
			return fmt.Errorf("corpus source input %q has no unique recorded entry", name)
		}
		seen[name] = true
	}
	return checkRegressionInventory(inventory, names)
}

func checkSurfaceInventory(inventory corpusInventory, keys map[string]bool) error {
	for _, surface := range []string{"cli", "mcp", "http", "schema", "canonical", "randstream", "primitive"} {
		if len(inventory.Surfaces[surface]) == 0 {
			return fmt.Errorf("corpus surface inventory lacks %q", surface)
		}
	}
	for surface, commands := range inventory.Surfaces {
		if len(inventory.MissingSurface[surface]) != 0 {
			return fmt.Errorf("corpus surface %q is incomplete", surface)
		}
		for _, command := range commands {
			if !keys[surface+" "+command] {
				return fmt.Errorf("corpus surface %q command %q has no case", surface, command)
			}
		}
	}
	return nil
}

func checkRegressionInventory(inventory corpusInventory, names map[string]bool) error {
	regressions := inventory.Regressions
	if !regressions.Complete || regressions.TestCount <= 0 || regressions.InputCount <= 0 || regressions.InputCount != len(regressions.Origins) {
		return errors.New("corpus regression inventory is incomplete")
	}
	if !hexDigest(regressions.SourceIdentity.TestTree, 40) || !hexDigest(regressions.SourceIdentity.CollectorSHA256, 64) {
		return errors.New("corpus regression inventory has invalid provenance")
	}
	for identity, origins := range regressions.Origins {
		if !hexDigest(identity, 64) || !names["regression/"+identity] || len(origins) == 0 || slices.Contains(origins, "") {
			return fmt.Errorf("regression input %q has no recorded case or test origin", identity)
		}
	}
	return nil
}

func inventoriedCases(cases []Case) (keys, digests, names map[string]bool) {
	keys = map[string]bool{}
	digests = map[string]bool{}
	names = map[string]bool{}
	for _, c := range cases {
		command := c.Command
		if c.Surface == "schema" && len(c.Args) == 1 {
			command = c.Args[0]
		}
		keys[c.Surface+" "+command] = true
		names[c.Name] = true
		for _, content := range c.Files {
			sum := sha256.Sum256(content)
			digests[hex.EncodeToString(sum[:])] = true
		}
	}
	return keys, digests, names
}
