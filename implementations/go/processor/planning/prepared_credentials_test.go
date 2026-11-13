package planning_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPreparedSelectionKeepsCredentialMaterialAndPurposeFrozen(t *testing.T) {
	original := preparedSelectionTargetFixture(t, `name: prepared-credentials
nodes:
 host: {type: compute}
accounts:
 admin:
  node: host
  username: admin
  credential_bindings:
  - credential_id: login
    purpose: primary_authentication
    auth_method: password
    material: {classification: secret_fixture, value: weak-fixture}
`, func(record map[string]any) {
		provisioner := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
		provisioner["supported_account_features"] = append(requireType[[]any](t, provisioner["supported_account_features"]), "credential_bindings")
	})
	unchanged, violation, err := planning.CheckPreparedSelection(original, original.Provisioning())
	requireNoError(t, err)
	if unchanged == nil || violation != "" {
		t.Fatalf("unchanged credential selection refused: %s", violation)
	}
	for _, mutation := range []string{"material", "purpose"} {
		t.Run(mutation, func(t *testing.T) {
			selected := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) {
				mutatePreparedCredentials(t, record, mutation)
			})
			admitted, violation, err := planning.CheckPreparedSelection(original, selected)
			requireNoError(t, err)
			if admitted != nil || violation != "Backend preparation changed a value outside realization authority." {
				t.Fatalf("credential %s substitution accepted: %s", mutation, violation)
			}
		})
	}
}

func mutatePreparedCredentials(t *testing.T, record map[string]any, mutation string) {
	t.Helper()
	for _, item := range requireType[[]any](t, record["operations"]) {
		operation := requireType[map[string]any](t, item)
		if operation["resource_type"] != "account-placement" {
			continue
		}
		payload := requireType[map[string]any](t, operation["payload"])
		spec := requireType[map[string]any](t, payload["spec"])
		credential := requireType[map[string]any](t, requireType[[]any](t, spec["credential_bindings"])[0])
		if mutation == "material" {
			requireType[map[string]any](t, credential["material"])["value"] = "substituted-fixture"
		} else {
			credential["purpose"] = "administrative_authentication"
		}
	}
}
