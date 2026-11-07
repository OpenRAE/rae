package admission

import (
	"regexp"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

var hostDrive = regexp.MustCompile(`^[A-Za-z]:[\\/]`)

func resolvedImportProvenance(v any) error {
	parts := strings.Split(stringAt(v, "module_id"), "/")
	if len(parts) != 2 || !moduleIdentifierPart(parts[0]) || !moduleIdentifierPart(parts[1]) {
		return invalid()
	}
	bindings := array(at(v, "bindings"))
	keys, valid := identityKeys(bindings, "parameter", 1)
	if !valid || len(keys) != len(bindings) {
		return invalid()
	}
	for _, field := range []string{"requested_digest", "manifest_digest", "content_digest", "export_hash"} {
		if value := stringAt(v, field); value != "" && !digest.Valid(value) {
			return invalid()
		}
	}
	for _, field := range []string{"requested_source", "resolved_source"} {
		source := stringAt(v, field)
		if absoluteHostSource(source) || registryUserinfo(source) {
			return invalid()
		}
	}
	return nil
}
func moduleIdentifierPart(value string) bool {
	return value != "__private" && address.Valid("x."+value)
}
func absoluteHostSource(value string) bool {
	for _, prefix := range []string{"local:", "file:"} {
		if rest, found := strings.CutPrefix(value, prefix); found {
			value = rest
			break
		}
	}
	return strings.HasPrefix(value, "/") || strings.HasPrefix(value, `\`) || strings.HasPrefix(value, "~/") || strings.HasPrefix(value, `~\`) || hostDrive.MatchString(value)
}
func registryUserinfo(value string) bool {
	if !strings.HasPrefix(value, "oci:") && !strings.Contains(value, "@sha256:") {
		return false
	}
	value = strings.TrimPrefix(value, "oci:")
	if _, rest, found := strings.Cut(value, "://"); found {
		value = rest
	}
	authority, _, _ := strings.Cut(value, "/")
	return strings.Contains(authority, "@")
}
