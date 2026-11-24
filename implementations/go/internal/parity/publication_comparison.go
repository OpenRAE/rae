package parity

import (
	"encoding/json"
	"errors"
	"io/fs"
	"path"
	"strings"
)

// Publication digests and paths are stable except for the independently drawn
// nonce of a new immutable version directory. Validate that coordinate before
// projecting the nonce out of both observations. The runner never sees the oracle.
func compareCaseResults(c Case, want, got json.RawMessage) (string, error) {
	if c.Key() != "cli sdl publish" {
		return compareResults(want, got)
	}
	expected, err := publicationComparison(c.Args, want)
	if err != nil {
		return "", err
	}
	actual, err := publicationComparison(c.Args, got)
	if err != nil {
		return "", err
	}
	return compareResults(expected, actual)
}

func publicationComparison(args []string, raw json.RawMessage) (json.RawMessage, error) {
	value, err := decodeResult(raw)
	if err != nil {
		return nil, err
	}
	result, ok := value.(map[string]any)
	if !ok {
		return nil, errors.New("publication result is not an object")
	}
	if result["exit_code"] != json.Number("0") {
		return raw, nil
	}
	command, ok := moduleArguments(args)
	if !ok {
		return nil, errors.New("publication has invalid command arguments")
	}
	stdout, ok := result["stdout"].(map[string]any)
	if !ok {
		return nil, errors.New("publication has no result")
	}
	manifest, _ := stdout["manifest_digest"].(string)
	hash, tagged := strings.CutPrefix(manifest, "sha256:")
	if !tagged || !hexDigest(hash, 64) {
		return nil, errors.New("publication manifest digest is invalid")
	}
	layout, _ := stdout["layout_dir"].(string)
	id, _ := stdout["module_id"].(string)
	version, _ := stdout["module_version"].(string)
	prefix := path.Join(command.output, strings.ReplaceAll(id, "/", "_")+"-"+version+".oci", "versions")
	coordinate := path.Base(layout)
	stable, nonce, ok := strings.Cut(coordinate, "-")
	if !fs.ValidPath(layout) || id == "" || version == "" || path.Dir(layout) != prefix || !ok || stable != hash[:20] || !hexDigest(nonce, 20) {
		return nil, errors.New("publication version coordinate is invalid")
	}
	generated, ok := result["generated_files"].(map[string]any)
	if !ok || len(generated) != 1 {
		return nil, errors.New("publication generated files are incomplete")
	}
	index, present := generated[path.Join(layout, "index.json")]
	if !present {
		return nil, errors.New("publication index does not belong to its immutable layout")
	}
	projected := path.Join(prefix, stable+"-<nonce>")
	stdout["layout_dir"] = projected
	result["generated_files"] = map[string]any{path.Join(projected, "index.json"): index}
	return json.Marshal(result)
}
