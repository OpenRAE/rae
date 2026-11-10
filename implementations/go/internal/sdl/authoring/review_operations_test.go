package authoring

import (
	"encoding/json"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

func TestPublicationRejectsLockDependentGraph(t *testing.T) {
	parser := operationParser(t)
	for _, name := range []string{"main.yaml", "sub/module.yaml"} {
		t.Run(name, func(t *testing.T) {
			files := publicationAliasFiles(t, parser, name)
			if _, err := parser.Decode(Request{Source: files["main.yaml"].Data, Name: "main.yaml", FS: files}); err != nil {
				t.Fatalf("workspace alias must compose before testing publication: %v", err)
			}
			entry, captured, err := parser.AdmitModuleSources(t.Context(), files, "main.yaml")
			if err == nil || entry != "" || captured != nil {
				t.Fatal("publication accepted a graph that depends on an omitted workspace lock")
			}
		})
	}
}

func publicationAliasFiles(t *testing.T, parser *Parser, name string) fstest.MapFS {
	t.Helper()
	prefix := ""
	if name != "main.yaml" {
		prefix = "sub/"
	}
	local := "name: parent\nmodule: {id: example/parent, version: 1.0.0, exports: {}}\nimports: [{source: 'local:child.yaml', namespace: child}]\n"
	child := "name: child\nmodule: {id: example/child, version: 1.0.0, exports: {nodes: [host]}}\nnodes: {host: {type: compute}}\n"
	files := fstest.MapFS{name: {Data: []byte(local)}, prefix + "child.yaml": {Data: []byte(child)}}
	lock, err := module.ResolveLock(t.Context(), files, name, module.DefaultPolicy(), parser)
	if err != nil {
		t.Fatal(err)
	}
	record := lock.Imports[0]
	raw, err := json.Marshal(map[string]any{"schema_version": "raes-lock/v1", "imports": []any{map[string]any{"source": record.Source, "namespace": record.Namespace, "requested_version": record.RequestedVersion, "resolved_source": record.ResolvedSource, "module_id": record.ModuleID, "module_version": record.ModuleVersion, "manifest_digest": record.ManifestDigest, "content_digest": record.ContentDigest, "export_hash": record.ExportHash, "signer_id": record.SignerID}}})
	if err != nil {
		t.Fatal(err)
	}
	files[prefix+module.LockfileName] = &fstest.MapFile{Data: raw}
	files[name].Data = []byte(strings.ReplaceAll(local, "local:child.yaml", "locked:child.yaml"))
	if name != "main.yaml" {
		files["main.yaml"] = &fstest.MapFile{Data: []byte("name: root\nmodule: {id: example/root, version: 1.0.0, exports: {}}\nimports: [{path: sub/module.yaml, namespace: parent}]\n")}
	}
	return files
}

func TestTransformationKeepsImportedProvenance(t *testing.T) {
	parser := operationParser(t)
	document := importedProvenanceDocument(t, parser)
	for _, operation := range []string{renameProfile, removeProfile} {
		t.Run(operation, func(t *testing.T) {
			transformed := transformImportedDeclaration(t, parser, document, operation)
			concrete, err := parser.Instantiate(transformed, nil, "")
			if err != nil {
				t.Fatal(err)
			}
			assertTransformedProvenance(t, concrete, operation == renameProfile)
		})
	}
}

func importedProvenanceDocument(t *testing.T, parser *Parser) *Document {
	t.Helper()
	root := []byte("name: root\nimports: [{path: child.yaml, namespace: lib, parameters: {os: linux, port: 9100}}]\n")
	child := []byte("name: child\nmodule: {id: example/child, version: 1.0.0, exports: {nodes: [host, other]}, parameters: [ram, label, os, port]}\nvariables:\n  ram: {type: string, default: '512 MiB', allowed_values: ['512 MiB', '1 GiB']}\n  label: {type: string, default: host}\n  os: {type: string, required: true, allowed_values: [linux, windows]}\n  port: {type: integer, required: true}\nnodes: {host: {type: compute, os: '${os}', description: '${label}', resources: {ram: '${ram}', cpu: 1}, runtime: {service_listeners: [{service_listener_id: probe, port: '${port}'}]}}, other: {type: switch}}\n")
	child = append(child, []byte("realization:\n  default: closed\n  scopes: [{field_pointer: /nodes/host, posture: open}]\n  constraints: [{concern: compute-substrate, field_pointer: /nodes/host, posture: open}]\n")...)
	files := fstest.MapFS{"main.yaml": {Data: root}, "child.yaml": {Data: child}}
	document, err := parser.Decode(Request{Source: root, Name: "main.yaml", FS: files})
	if err != nil {
		t.Fatal(err)
	}
	document, _, err = parser.Validate(document)
	if err != nil {
		t.Fatal(err)
	}
	return document
}

func transformImportedDeclaration(t *testing.T, parser *Parser, source *Document, operation string) *Document {
	t.Helper()
	request := map[string]any{termOperationProfile: operation, "request": map[string]any{"target_address": "nodes.lib.host"}}
	if operation == renameProfile {
		object(request["request"])["new_local_name"] = "frontend"
	} else {
		request[policyField] = map[string]any{termAllowedLossKinds: []string{termDeclarationRemoved}}
	}
	raw, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	transformed, _, err := parser.Transform(source, raw)
	if err != nil || transformed == nil {
		t.Fatalf("transformation failed: %v", err)
	}
	return transformed
}

func assertTransformedProvenance(t *testing.T, concrete *Document, renamed bool) {
	t.Helper()
	var payload map[string]any
	if json.Unmarshal(concrete.JSON(), &payload) != nil {
		t.Fatal("invalid concrete output")
	}
	provenance := object(payload["instantiation_provenance"])
	paths := map[string]bool{}
	for _, raw := range array(provenance[termExplicitness]) {
		name := text(object(raw)["model_path"])
		if modelPathWithin(name, "nodes.lib.host") {
			t.Fatal("concrete provenance retained the absent declaration")
		}
		paths[name] = true
	}
	if !paths["nodes.lib.other.type"] || renamed && !paths["nodes.lib.frontend.type"] {
		t.Fatal("concrete provenance lost retained declaration explicitness")
	}
	assertTransformedPointers(t, provenance, renamed)
}

func assertTransformedPointers(t *testing.T, provenance map[string]any, renamed bool) {
	t.Helper()
	for _, field := range []string{termCapabilityConstraints, termParameterDerivations, termRealizationConstraints, termRealizationDesignations} {
		rows := array(provenance[field])
		retargeted := false
		for _, raw := range rows {
			pointer := text(object(raw)[fieldPointerField])
			if strings.HasPrefix(pointer, "/nodes/lib.host") || strings.HasPrefix(pointer, "/infrastructure/lib.host") {
				t.Fatalf("%s retained an obsolete field pointer", field)
			}
			retargeted = retargeted || strings.HasPrefix(pointer, "/nodes/lib.frontend") || strings.HasPrefix(pointer, "/infrastructure/lib.frontend")
		}
		if renamed && !retargeted {
			t.Fatalf("%s lost the replacement declaration's field pointer", field)
		}
	}
}
