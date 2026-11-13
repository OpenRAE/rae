package processor

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

const preparedResourceFixture = `{
 "nodes":{"host":{"type":"compute","runtime":{"environment":[{"name":"MODE","value_classification":"plain","provenance":"runtime","value_from":{"generated_artifact":"generated_artifacts.token","output":"value"}}]}}},
 "infrastructure":{},
 "resources":{"provision.generated-artifact.token":{"resource_type":"generated-artifact","payload":{"name":"token","spec":{
  "generator":"random_value","lifecycle":"reuse_valid","provenance":"test","regeneration_scope":"once",
  "random_value":{"alphabet":"hex_lower","length":32},"outputs":[{"name":"value","path":"token","sensitivity":"public"}],"consumers":[],
  "environment_consumers":[{"node":"host","target_address":"provision.node.host","delivery_mode":"environment","output":"value","environment_variable":"MODE"}]
 }}}}
}`

func preparedContextTestRecord(t *testing.T, input any) map[string]any {
	t.Helper()
	record, ok := input.(map[string]any)
	if !ok {
		t.Fatalf("expected native object, got %T", input)
	}
	return record
}

func TestPreparedResourceContextValidatesGrantsBeforeRemovingCompilerFields(t *testing.T) {
	input := decodeProjection([]byte(preparedResourceFixture))
	owner, err := processorAdmissionOwner()
	if err != nil {
		t.Fatal(err)
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		t.Fatal(err)
	}
	context, err := PreparedResourceContext(fragment)
	if err != nil {
		t.Fatal(err)
	}
	artifact := preparedContextTestRecord(t, preparedContextTestRecord(t, context.Document())["generated_artifacts"])["token"]
	if _, retained := preparedContextTestRecord(t, artifact)["environment_consumers"]; retained {
		t.Fatal("compiler grant field retained in native SDL model")
	}
	resources := preparedContextTestRecord(t, input["resources"])
	spec := preparedContextTestRecord(t, preparedContextTestRecord(t, resources["provision.generated-artifact.token"])["payload"])["spec"]
	rows, ok := preparedContextTestRecord(t, spec)["environment_consumers"].([]any)
	if !ok || len(rows) != 1 {
		t.Fatal("consumer fixture")
	}
	preparedContextTestRecord(t, rows[0])["target_address"] = "provision.node.absent"
	fragment, err = admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := PreparedResourceContext(fragment); err == nil {
		t.Fatal("forged grant was stripped before validation")
	}
}

func TestPreparedResourceContextChecksLiveOutputAndClosedGrantSemantics(t *testing.T) {
	owner, err := processorAdmissionOwner()
	if err != nil {
		t.Fatal(err)
	}
	for _, mutation := range []string{"secret-output", "producer-private", "foreign-output", "foreign-mode", "extra-grant-field"} {
		t.Run(mutation, func(t *testing.T) {
			input := decodeProjection([]byte(preparedResourceFixture))
			resources := preparedContextTestRecord(t, input["resources"])
			spec := preparedContextTestRecord(t, preparedContextTestRecord(t, preparedContextTestRecord(t, resources["provision.generated-artifact.token"])["payload"])["spec"])
			mutatePreparedResourceFixture(t, spec, mutation)
			fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
			if err != nil {
				t.Fatal(err)
			}
			if _, err := PreparedResourceContext(fragment); err == nil {
				t.Fatal("live output/grant defect was admitted")
			}
		})
	}
}

func mutatePreparedResourceFixture(t *testing.T, spec map[string]any, mutation string) {
	t.Helper()
	outputs, ok := spec["outputs"].([]any)
	if !ok || len(outputs) != 1 {
		t.Fatal("outputs fixture")
	}
	grants, ok := spec["environment_consumers"].([]any)
	if !ok || len(grants) != 1 {
		t.Fatal("grants fixture")
	}
	switch mutation {
	case "secret-output":
		preparedContextTestRecord(t, outputs[0])["sensitivity"] = "secret"
	case "producer-private":
		preparedContextTestRecord(t, outputs[0])["visibility"] = "producer_private"
	case "foreign-output":
		preparedContextTestRecord(t, grants[0])["output"] = "absent"
	case "foreign-mode":
		preparedContextTestRecord(t, grants[0])["delivery_mode"] = "mount"
	case "extra-grant-field":
		preparedContextTestRecord(t, grants[0])["grant"] = true
	}
}
