# Maintain SDL semantic fixtures

Use this procedure to change the [published SDL semantic vectors](../../contracts/fixtures/sdl/semantic-vectors-v1/README.md).
You need the repository's Go toolchain, `jq`, and `sha256sum`.
No Python recorder is required.
Run commands from the repository root unless a step changes the directory.

1. Edit a shard under `contracts/fixtures/sdl/semantic-vectors-v1/`.
   Give each new case a unique name.
   Set the source and expected results from the SDL specifications.
   Preserve ordered diagnostics, literal source text, and distinctions between absent, null, and empty values.
   Keep the historical provenance file unchanged.

2. Check each changed shard's count, byte size, and raw-byte hash.
   This example uses the first shard.

   ```shell
   cd contracts/fixtures/sdl/semantic-vectors-v1
   jq length semantics-000.json
   wc -c < semantics-000.json
   sha256sum semantics-000.json
   ```

   Each shard must contain at least one case and at most 460800 bytes.
   Use the next consecutive shard name when another shard is needed.
   The reader permits at most 128 shards.

3. Update each changed shard's `case_count` and `sha256` in `semantics.json`.
   Set the manifest's total `case_count` to the sum of its shard counts.
   Remove obsolete shard files when you remove their entries.
   Keep the format discriminator unchanged for compatible case additions.
   Review format changes separately.

4. Return to the repository root.
   Run the native inventory and semantic checks.

   ```shell
   cd ../../../..
   go -C implementations/go test ./internal/sdl/authoring \
     -run '^Test(SemanticReference|SemanticFixtureIntegrity|SemanticFixtureRecordShapes)$' -count=1
   ```

   A failure identifies invalid fixture data or a difference from the expected semantic result.
   Correct the cause before you continue.
   Do not copy observed implementation output into an expectation to clear a failure.

5. Refresh the packaged copy through the existing generator.

   ```shell
   go -C implementations/tooling/go build -o /tmp/raes-contractgen ./cmd/contractgen
   /tmp/raes-contractgen
   /tmp/raes-contractgen -check
   go -C implementations/go test ./internal/sdl/authoring \
     -run '^TestSemanticFixturePackaging$' -count=1
   ```

   The packaging test compares the published files with their embedded copy.
   It also loads the packaged inventory from an empty working directory.

6. Review the fixture changes and generated files in the same pull request.
   Explain the specification basis for each changed expectation.
   Keep local tests targeted.
   CI runs the full verification suites.
