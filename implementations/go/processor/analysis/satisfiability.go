package analysis

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"path"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const satisfiabilityProfile = "raes-finite-domain-satisfiability-v1"

func readAnalysisSource(input *SourceInput) (sdl.SourceContext, error) {
	if input == nil || input.Options.Validate() != nil {
		return sdl.SourceContext{}, invalidAnalysis()
	}
	source := input.Source
	if !fs.ValidPath(source.Root) || source.Root == "." || source.FS != nil && source.Sources != nil {
		return sdl.SourceContext{}, invalidAnalysis()
	}
	raw := source.RootBytes
	if raw == nil && source.Sources != nil {
		raw = source.Sources[source.Root]
	}
	if raw == nil && source.FS != nil {
		var err error
		raw, err = readSourceFile(source.FS, source.Root, input.Options.Limits.MaxInputBytes)
		if err != nil {
			return sdl.SourceContext{}, err
		}
	}
	if raw == nil || int64(len(raw)) > input.Options.Limits.MaxInputBytes {
		return sdl.SourceContext{}, invalidAnalysis()
	}
	source.RootBytes = slices.Clone(raw)
	return source, nil
}
func solverConfiguration() map[string]any {
	return map[string]any{
		fieldProfile: "raes-z3-finite-domain/v2", "engine": "z3", "package": "raes-go-z3-smtlib", "package_version": initialVersion, "engine_version": "4.16.0", "logic": "QF_LIA", "random_seed": 0, "timeout_ms": 5000, "threads": 1, "auto_config": false, "model": true, termUnsatCore: true, "witness_selection": "canonical-lexicographic/v1", "core_reduction": "sorted-deletion-subset-minimal/v1",
	}
}
func analyzeSatisfiability(ctx context.Context, request Request) (Result, error) {
	if len(request.Options) > 0 && (len(request.Options) != 1 || request.Options[fieldProfile] != satisfiabilityProfile) {
		return Result{}, fault.New(fault.Operational, "analysis-profile", nil)
	}
	source, err := readAnalysisSource(request.Source)
	if err != nil {
		return Result{}, err
	}
	scenario, err := sdl.ParseSourceWithContext(ctx, source, request.Source.Options)
	if err != nil {
		return Result{}, err
	}
	translated, findings, err := translateScenario(scenario, digest.SHA256(source.RootBytes))
	if err != nil {
		return Result{}, err
	}
	document, err := satisfiabilityDocument(scenario, source.Root, translated, findings)
	if err != nil {
		return Result{}, err
	}
	if len(findings) > 0 {
		document[fieldOutcome] = outcomeUnsupported
		document[outcomeUnsupported] = map[string]any{fieldProfile: "raes-satisfiability-unsupported/v1", fieldReasonCodes: diagnosticCodes(findings)}
	} else if err = completeSatisfiability(ctx, request.Solver, scenario, translated, document); err != nil {
		return Result{}, err
	}
	result, err := admitOutput("scenario-satisfiability-evidence-v2", document, witnessPhaseOwner{ctx: ctx})
	result.Diagnostics = findings
	return result, err
}

func readSourceFile(filesystem fs.FS, name string, limit int64) ([]byte, error) {
	file, err := filesystem.Open(name)
	if err != nil {
		return nil, fault.New(fault.Operational, "analysis-source-read", nil)
	}
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() {
		_ = file.Close()
		return nil, invalidAnalysis()
	}
	raw, err := io.ReadAll(io.LimitReader(file, limit))
	var probe [1]byte
	count, probeErr := file.Read(probe[:])
	if err == nil && (count != 0 || !errors.Is(probeErr, io.EOF)) {
		_ = file.Close()
		return nil, invalidAnalysis()
	}
	closeErr := file.Close()
	if err != nil || closeErr != nil {
		return nil, fault.New(fault.Operational, "analysis-source-read", nil)
	}
	return raw, nil
}

func satisfiabilityDocument(scenario sdl.Scenario, sourceName string, translated constraintModel, findings []diagnostic.Diagnostic) (map[string]any, error) {
	normalizedDigest, err := hash(translated)
	if err != nil {
		return nil, err
	}
	config := solverConfiguration()
	configDigest, err := hash(config)
	if err != nil {
		return nil, err
	}
	imports := []any{}
	modelBytes, err := sdl.ModelBytes(scenario)
	if err != nil {
		return nil, err
	}
	modelView, err := decodeObject(modelBytes, 16<<20)
	if err != nil {
		return nil, err
	}
	if expanded := object(modelView["expansion_provenance"]); expanded != nil {
		if values := array(expanded[termImports]); values != nil {
			imports = values
		}
	}
	document := map[string]any{fieldProfile: "scenario-satisfiability-evidence/v2", fieldAnalysisProfile: satisfiabilityProfile, fieldSource: map[string]any{"source_id": path.Base(sourceName), "byte_digest": translated.SourceDigest}, termAuthoredDigest: translated.AuthoredDigest, termImports: imports, "normalized_model": translated, fieldNormalizedDigest: normalizedDigest, "solver_configuration": config, "solver_configuration_digest": configDigest, fieldDiagnostics: diagnosticsDocument(findings), termWitness: nil, termUnsatCore: nil, outcomeUnsupported: nil}

	return document, nil
}

func completeSatisfiability(ctx context.Context, solver *Solver, scenario sdl.Scenario, translated constraintModel, document map[string]any) error {
	solution, err := solver.solve(ctx, translated)
	if err != nil {
		return err
	}
	if solution.assignment != nil {
		return satisfiabilityWitness(scenario, solution.assignment, document)
	}
	document[fieldOutcome] = "unsatisfiable"
	document[termUnsatCore] = map[string]any{fieldProfile: "raes-unsatisfiable-core/v1", "clause_ids": solution.core, "minimality": "subset-minimal"}
	return nil
}

func satisfiabilityWitness(scenario sdl.Scenario, assignment, document map[string]any) error {
	instance, err := sdl.InstantiateWithProfile(scenario, assignment, satisfiabilityProfile)
	if err != nil {
		return err
	}
	snapshotRaw, err := sdl.CanonicalBytes(instance)
	if err != nil {
		return err
	}
	snapshot, err := decodeObject(snapshotRaw, 8<<20)
	if err != nil {
		return err
	}
	snapshot[fieldProfile] = "raes-sdl-instantiated-snapshot/v3"
	snapshotDigest, err := hash(snapshot)
	if err != nil {
		return err
	}
	document[fieldOutcome] = "satisfiable"
	document[termWitness] = map[string]any{fieldProfile: "raes-satisfiability-witness/v2", "snapshot": snapshot, termSnapshotDigest: snapshotDigest}
	return nil
}
