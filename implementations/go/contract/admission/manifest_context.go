package admission

// ApparatusManifestContext supplies the selected manifest payloads and their
// canonical digests from the independently trusted manifest loader.
type ApparatusManifestContext interface {
	ProcessorManifest() []byte
	BackendManifest() []byte
	ProcessorManifestDigest() string
	BackendManifestDigest() string
}
