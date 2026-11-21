package admission

import (
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// CheckBackendContractVersions checks an explicit opt-in against the existing
// governed manifest catalog. It installs no provider and grants no authority.
func CheckBackendContractVersions(versions []string) error {
	if CheckTransportTree(versions, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return invalid()
	}
	return require(declaredManifestContracts(jsonStrings(versions), componentBackend))
}
