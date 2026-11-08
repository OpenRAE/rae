CLI reference
=============

``raes`` is the installed Python command.
Its command groups are ``sdl``, ``processor``, ``conformance``, ``semantic`` and ``runtime``.
``raes-mcp`` is a separate :doc:`MCP entry point <mcp>`.
For procedures, use the :doc:`command guide <../guides/cli>`.

Uppercase names below are required positional arguments.
Brackets mark optional arguments or options.
Each group and leaf command accepts ``--help``.
The reference describes registered commands, not the Python signatures of their callbacks.

Main CLI
--------

.. py:module:: raes_cli.main
   :no-index-entry:

.. code-block:: text

   raes [--version|-V] [--log-level LEVEL] COMMAND [ARGS]...

``--version`` or ``-V`` prints ``raes VERSION`` and exits successfully.
``--log-level`` accepts ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR`` or ``CRITICAL``, without case sensitivity.
Its default is ``WARNING``.
Operational logs go to stderr.
``--show-completion`` prints shell completion code.
``--install-completion`` installs completion for the current shell and can change its configuration.
The default invocation shows help rather than performing an operation.

Commands write their result to stdout unless stated otherwise.
Parser usage failures normally exit ``2``.
Unexpected failures caught at the installed application boundary exit ``70`` with a value-free log on stderr.
Other failures use the command-family rules below.
The semantic taxonomy does not apply to every command.

Semantic commands
-----------------

.. py:module:: raes_cli.semantic
   :no-index-entry:

.. code-block:: text

   raes semantic OPERATION SOURCE [--contract ID] [--output human|json]
       [--migration-policy reject|accept]

``SOURCE`` is a path or ``-`` for stdin.
``--contract`` defaults to ``sdl-yaml/v1``; portable JSON requires its published contract ID.
``--output`` defaults to ``human`` and ``--migration-policy`` defaults to ``reject``.
``accept`` enables recognized legacy SDL migration syntax only.
The commands do not acquire imported modules or write files.
SDL input is bounded by ``SDLParserLimits.max_input_bytes``; portable JSON uses a separate 8,388,608-byte limit.

.. list-table:: Registered operations
   :header-rows: 1
   :widths: 20 80

   * - Operation
     - Result and boundary
   * - ``raes semantic parse``
     - Bounded decoding and typed construction, without a validity claim.
   * - ``raes semantic validate``
     - Structural and semantic admission by the selected owner.
   * - ``raes semantic normalize``
     - Deterministic normalized SDL representation and provenance.
   * - ``raes semantic resolve``
     - Local SDL declaration resolution; no import acquisition.
   * - ``raes semantic compile``
     - Typed SDL runtime-model summary; no execution.
   * - ``raes semantic transform``
     - SDL transformation; requires ``--transform canonical|format``.
   * - ``raes semantic inspect``
     - Admitted artifact summary with raw values excluded.
   * - ``raes semantic conformance``
     - Local owner checks; no target invocation.

Portable JSON supports ``validate``, ``inspect`` and ``conformance``.
An unsupported operation returns a typed refusal.
JSON mode emits one deterministically ordered JSON object and a newline.
It includes operation, status, contract selection, profile metadata, provenance, payload and diagnostics.
Human mode prints content or an operation status to stdout and diagnostics to stderr.

.. list-table:: Semantic exit codes
   :header-rows: 1
   :widths: 15 85

   * - Code
     - Meaning
   * - ``0``
     - The selected operation succeeded within its stated boundary.
   * - ``1``
     - Input failed the selected admission checks.
   * - ``2``
     - Usage or contract selection was invalid.
   * - ``3``
     - The selected contract or profile does not support the operation.
   * - ``4``
     - Input could not be read within its bounds.
   * - ``70``
     - An unexpected internal failure occurred.

SDL commands
------------

.. py:module:: raes_cli.sdl
   :no-index-entry:

These commands use file-backed SDL and module-registry behavior.
They are distinct from the offline semantic command contract.
``PATH`` must exist and be readable.

``raes sdl format PATH [--write|--check]``
    Returns canonical ``sdl-yaml/v1`` text to stdout by default.
    ``--write`` replaces the source and prints its path.
    ``--check`` writes nothing and exits ``1`` when the source is not canonical.
    The two options are mutually exclusive; that usage failure exits ``2``.
    Recognized legacy syntax produces diagnostics on stderr.
    File-backed imports can trigger module acquisition.

``raes sdl resolve PATH [--lockfile PATH]``
    Resolves imports, writes the lockfile and prints its path.
    The default file is ``raes.lock.json`` beside the source.
    It creates the output parent directory when needed.
    Registry or input refusal exits ``1``.

``raes sdl verify-imports PATH``
    Compares the adjacent lockfile with current resolution, then parses the source.
    Success prints ``imports verified``.
    A missing or stale lockfile is a usage refusal; import or input failure exits ``1``.
    Resolution can read trust settings and acquire modules.

``raes sdl publish PATH [--output-dir DIR] [--signer-id ID] [--private-key FILE]``
    Writes a local immutable OCI layout and prints the result as JSON.
    ``--output-dir`` defaults to ``dist`` and ``--signer-id`` to an empty string.
    No signing key is selected by default.
    A supplied key file must exist and be readable.
    The returned ``layout_dir`` is the usable layout path.
    This command creates a local package; it does not push it to a remote registry.
    Input, conflict or operational refusal exits ``1``.

Processor commands
------------------

.. py:module:: raes_cli.processor
   :no-index-entry:

These commands inspect declarations, plans or finite analyses.
They do not apply a plan or provision a backend.
File-backed SDL can still acquire imports.

``raes processor manifest``
    Prints the reference processor manifest as JSON.
    It has no command-specific arguments or options.

``raes processor plan SDL --format json [--manifest FILE]``
    Compiles and plans a readable SDL file.
    ``--format json`` is required.
    The default manifest is the reference dry-run backend manifest.
    ``--manifest`` selects bounded UTF-8 ``backend-manifest-v2`` JSON.
    The result contains scenario name, three domain plans and diagnostics.
    An invalid plan is still emitted and exits ``1``.
    A malformed manifest is a usage refusal.

``raes processor reconcile BASELINE CANDIDATE --format json [--manifest FILE]``
    Plans two readable SDL files against the same manifest.
    ``--format json`` is required; manifest selection matches ``processor plan``.
    Output reports status, assumed baseline snapshot, diagnostics, action counts and operations.
    The snapshot is planned state, not backend readback.
    Rejection exits ``1``; malformed options or manifest input are usage refusals.

``raes processor satisfiability SDL [--profile ID]``
    Reads an SDL file and prints replayable satisfiability evidence as JSON.
    The default profile is ``raes-finite-domain-satisfiability-v1``.
    Exit ``0`` covers both satisfiable and unsatisfiable conclusions.
    Exit ``2`` means unsupported input; exit ``1`` means an input or operational failure.

``raes processor exploit-path INPUT_JSON [--profile ID]``
    Reads an exploit-path input file and prints typed analysis evidence as JSON.
    The default profile is ``raes-exploit-path-analysis-v1``.
    Exit ``0`` covers a completed valid or invalid path result.
    Exit ``2`` means unsupported input; exit ``1`` means malformed input or operational failure.

Conformance commands
--------------------

.. py:module:: raes_cli.conformance
   :no-index-entry:

``raes conformance backend [--profile ID] [--fixtures-root DIR] [--profiles-root DIR] [--format json|text]``
    Runs the published backend contract fixture suite.
    The default profile is ``orchestration-evaluation`` and output format is ``json``.
    Defaults use the packaged contract corpus.
    Overrides select the fixture and profile trees.
    A new profile ID requires its profile JSON; it need not be a Python enum member.
    Failed cases or top-level diagnostics exit ``1`` after the report.
    An unreadable fixture file exits ``1`` without a report.

``raes conformance processor [--feature NAME]... [--manifest FILE] [--format json|text]``
    Checks the reference processor with finite positive and negative SDL inputs.
    Features default to ``compilation`` and ``planning``.
    Repeat ``--feature`` to replace that selection.
    Manifest selection defaults to the reference dry-run backend; output defaults to ``json``.
    A failing report exits ``1``.
    The manifest is a planning input; no backend execution occurs.

Runtime store commands
----------------------

These commands maintain an offline local SQLite store under its exclusive lease.
``--target TEXT`` and ``--run-scope TEXT`` are required for each command.
The values must match the intended store scopes.
Do not run maintenance against a store used by a live runtime.

``raes runtime store check STORE_PATH --target TEXT --run-scope TEXT``
    Validates the store without replacing it.

``raes runtime store backup STORE_PATH BACKUP_PATH --target TEXT --run-scope TEXT [--replace]``
    Creates a consistent SQLite backup.
    Existing destinations are refused unless ``--replace`` is selected.

``raes runtime store restore BACKUP_PATH STORE_PATH --target TEXT --run-scope TEXT [--replace]``
    Validates the backup and restores the offline store.
    Existing destinations are refused unless ``--replace`` is selected.

Success prints ``control-plane-store-OPERATION-succeeded`` and exits ``0``.
A shared runtime refusal prints ``control-plane-store-OPERATION-failed`` to stderr and exits ``1``.
The output does not disclose store contents or paths.
See :doc:`runtime reference <runtime>` for store types and lifecycle boundaries.
