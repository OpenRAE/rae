package module

import (
	"encoding/json"
	"os"
	"strconv"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type policyVersionReference struct {
	Policies []struct {
		Source   string               `json:"source"`
		Accepted bool                 `json:"accepted"`
		Expected policyReferenceValue `json:"expected"`
	} `json:"policies"`
	Versions []struct {
		Request  string `json:"request"`
		Actual   string `json:"actual"`
		Valid    bool   `json:"valid"`
		Accepted bool   `json:"accepted"`
	} `json:"versions"`
}

type policyReferenceValue struct {
	SchemaVersion             string                            `json:"SchemaVersion"`
	AllowUnsignedLocalSources bool                              `json:"AllowUnsignedLocalSources"`
	Registries                map[string]registryReferenceValue `json:"Registries"`
}
type registryReferenceValue struct {
	RequireSignatures bool              `json:"RequireSignatures"`
	AllowInsecureHTTP bool              `json:"AllowInsecureHTTP"`
	TrustedSigners    map[string]string `json:"TrustedSigners"`
}

func (p policyReferenceValue) native() Policy {
	result := Policy{SchemaVersion: p.SchemaVersion, AllowUnsignedLocalSources: p.AllowUnsignedLocalSources, Registries: map[string]RegistryTrust{}}
	for name, rule := range p.Registries {
		result.Registries[name] = RegistryTrust(rule)
	}
	return result
}

func readPolicyVersions(t *testing.T) policyVersionReference {
	t.Helper()
	raw, err := os.ReadFile("testdata/policy-versions.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture policyVersionReference
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	return fixture
}

func TestWorkspacePolicyReference(t *testing.T) {
	for i, row := range readPolicyVersions(t).Policies {
		t.Run(strconv.Itoa(i), func(t *testing.T) {
			got, err := DecodePolicy([]byte(row.Source))
			if (err == nil) != row.Accepted {
				t.Fatalf("policy admission = %v; expected %v for %q", err, row.Accepted, row.Source)
			}
			if err == nil {
				if diff := cmp.Diff(row.Expected.native(), got); diff != "" {
					t.Fatal(diff)
				}
			}
		})
	}
}

func TestVersionRequestReference(t *testing.T) {
	for i, row := range readPolicyVersions(t).Versions {
		t.Run(strconv.Itoa(i), func(t *testing.T) {
			spec, err := ParseVersionRequirement(row.Request)
			if (err == nil) != row.Valid {
				t.Fatalf("request %q admission: %v", row.Request, err)
			}
			if err == nil && spec.Accepts(row.Actual) != row.Accepted {
				t.Fatalf("%q accepts %q: want %v", row.Request, row.Actual, row.Accepted)
			}
		})
	}
}
