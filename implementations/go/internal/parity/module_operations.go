package parity

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

type moduleCommand struct{ operation, name, lock, output, signer, key string }

func moduleOperationRunner() Runner {
	parser, loadErr := authoring.New(source.DefaultLimits())
	return func(ctx context.Context, c Case) (json.RawMessage, error) {
		if loadErr != nil {
			return nil, loadErr
		}
		command, ok := moduleArguments(c.Args)
		if !ok {
			return formatEnvelope(2, nil)
		}
		files, generated, err := prepareModuleCommand(ctx, parser, c, command)
		if err != nil {
			return nil, err
		}
		if files == nil {
			return formatEnvelope(2, nil)
		}
		var code int
		var stdout any
		switch command.operation {
		case termResolve:
			code, err = resolveModuleCommand(ctx, parser, files, command, generated)
		case "verify-imports":
			code, err = verifyModuleCommand(ctx, parser, files, command)
		case "publish":
			code, stdout, err = publishModuleCommand(ctx, parser, files, command, generated)
		}
		if err != nil {
			return nil, err
		}
		result := map[string]any{"exit_code": code, "stdout": stdout}
		if len(generated) > 0 {
			result["generated_files"] = generated
		}
		return json.Marshal(result)
	}
}

func resolveModuleCommand(ctx context.Context, parser *authoring.Parser, files fstest.MapFS, command moduleCommand, generated map[string]any) (int, error) {
	lock, err := module.ResolveLock(ctx, files, command.name, nil, parser)
	if err != nil {
		return moduleCommandFailure(err)
	}
	payload := lockPayload(lock)
	raw, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return 0, err
	}
	raw = append(raw, '\n')
	name := command.lock
	if name == "" {
		name = path.Join(path.Dir(command.name), module.LockfileName)
	}
	if !fs.ValidPath(name) {
		return 2, nil
	}
	if current, present := files[name]; !present || !bytes.Equal(current.Data, raw) {
		generated[name] = payload
	}
	files[name] = &fstest.MapFile{Data: raw}
	return 0, nil
}
func lockPayload(lock module.Lockfile) map[string]any {
	rows := []any{}
	for _, record := range lock.Imports {
		rows = append(rows, map[string]any{"source": record.Source, "namespace": record.Namespace, "requested_version": record.RequestedVersion, "resolved_source": record.ResolvedSource, "module_id": record.ModuleID, "module_version": record.ModuleVersion, "manifest_digest": record.ManifestDigest, "content_digest": record.ContentDigest, "export_hash": record.ExportHash, "signer_id": record.SignerID})
	}
	return map[string]any{"schema_version": lock.SchemaVersion, "imports": rows}
}
func verifyModuleCommand(ctx context.Context, parser *authoring.Parser, files fstest.MapFS, command moduleCommand) (int, error) {
	name := path.Join(path.Dir(command.name), module.LockfileName)
	raw, present := files[name]
	if !present {
		return 2, nil
	}
	existing, err := module.DecodeLockfile(raw.Data)
	if err != nil {
		return moduleCommandFailure(err)
	}
	expected, err := module.ResolveLock(ctx, files, command.name, nil, parser)
	if err != nil {
		return moduleCommandFailure(err)
	}
	if !cmp.Equal(existing, expected) {
		return 2, nil
	}
	document, err := parser.DecodeContext(ctx, authoring.Request{Source: files[command.name].Data, Name: command.name, FS: files})
	if err == nil {
		_, _, err = parser.Validate(document)
	}
	if err != nil {
		return moduleCommandFailure(err)
	}
	return 0, nil
}

func publishModuleCommand(ctx context.Context, parser *authoring.Parser, files fstest.MapFS, command moduleCommand, generated map[string]any) (int, any, error) {
	privateKey := []byte(nil)
	if command.key != "" {
		file, present := files[command.key]
		if !present {
			return 2, nil, nil
		}
		privateKey = file.Data
	}
	temporary, err := os.MkdirTemp("", "rae-module-parity-")
	if err != nil {
		return 0, nil, err
	}
	defer func() { _ = os.RemoveAll(temporary) }()
	registry, err := module.NewRegistry(filepath.Join(temporary, "cache"), module.DefaultPolicy(), nil)
	if err != nil {
		return 0, nil, err
	}
	defer func() { _ = registry.Close() }()
	if !fs.ValidPath(command.output) {
		return 2, nil, nil
	}
	publication, err := registry.Publish(ctx, files, command.name, filepath.Join(temporary, filepath.FromSlash(command.output)), command.signer, privateKey, parser)
	if err != nil {
		code, failure := moduleCommandFailure(err)
		return code, nil, failure
	}
	index, err := os.ReadFile(filepath.Join(publication.LayoutDir, "index.json"))
	if err != nil {
		return 0, nil, err
	}
	var payload any
	if err = json.Unmarshal(index, &payload); err != nil {
		return 0, nil, err
	}
	relative, err := filepath.Rel(temporary, publication.LayoutDir)
	if err != nil {
		return 0, nil, err
	}
	publication.LayoutDir = filepath.ToSlash(relative)
	generated[path.Join(publication.LayoutDir, "index.json")] = payload
	return 0, publication, nil
}

func materializeKeyRecipes(files fstest.MapFS) error {
	raw, present := files["input-recipes.json"]
	if !present {
		return nil
	}
	var recipes map[string]struct {
		Kind string `json:"kind"`
		Seed string `json:"seed_id"`
	}
	if err := json.Unmarshal(raw.Data, &recipes); err != nil {
		return err
	}
	for name, recipe := range recipes {
		if !fs.ValidPath(name) {
			return fs.ErrInvalid
		}
		var content []byte
		switch recipe.Kind {
		case "invalid-key":
			content = []byte("not a private key\n")
		case "public-test-ed25519":
			seed := sha256.Sum256([]byte(recipe.Seed))
			encoded, err := x509.MarshalPKCS8PrivateKey(ed25519.NewKeyFromSeed(seed[:]))
			if err != nil {
				return err
			}
			content = pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: encoded})
		default:
			return fs.ErrInvalid
		}
		files[name] = &fstest.MapFile{Data: content}
	}
	return nil
}

func moduleArguments(args []string) (moduleCommand, bool) {
	command := moduleCommand{output: "dist"}
	if len(args) < 3 || args[0] != "sdl" {
		return command, false
	}
	command.operation = args[1]
	options := map[string]*string{}
	switch command.operation {
	case termResolve:
		options["--lockfile"] = &command.lock
	case "verify-imports":
	case "publish":
		options = map[string]*string{"--output-dir": &command.output, "--signer-id": &command.signer, "--private-key": &command.key}
	default:
		return command, false
	}
	name, arguments, ok := operationArguments(args[2:], false)
	if !ok {
		return command, false
	}
	command.name = name
	for _, argument := range arguments {
		dest, known := options[argument.name]
		if !known {
			return command, false
		}
		*dest = argument.value
	}
	return command, true
}
func moduleCommandFailure(err error) (int, error) {
	if _, classified := fault.CategoryOf(err); classified {
		return 1, nil
	}
	return 0, err
}
func prepareModuleCommand(ctx context.Context, parser *authoring.Parser, c Case, command moduleCommand) (fstest.MapFS, map[string]any, error) {
	files := fstest.MapFS{}
	for name, raw := range c.Files {
		files[name] = &fstest.MapFile{Data: raw}
	}
	if _, present := files[command.name]; !present {
		return nil, nil, nil
	}
	if err := materializeKeyRecipes(files); err != nil {
		return nil, nil, err
	}
	var setup struct {
		Commands [][]string `json:"commands"`
	}
	if raw, present := files["setup.json"]; present {
		if err := json.Unmarshal(raw.Data, &setup); err != nil {
			return nil, nil, err
		}
	}
	generated := map[string]any{}
	for _, args := range setup.Commands {
		prepare, ok := moduleArguments(args)
		if !ok || prepare.operation != termResolve {
			return nil, nil, fs.ErrInvalid
		}
		if _, err := resolveModuleCommand(ctx, parser, files, prepare, generated); err != nil {
			return nil, nil, err
		}
	}
	return files, generated, nil
}
