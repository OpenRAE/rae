MCP reference
=============

``raes-mcp`` starts the installed Python Model Context Protocol server over its default stdio transport.
It has no application-specific command-line options.
Protocol output uses stdout; operational logs use stderr.
The server helps author, inspect, validate and dry-run SDL.
It does not expose participant cyber actions or start a live range.

Inputs, results and errors
--------------------------

Tools accept named JSON arguments.
Signatures below show required arguments without defaults.
Arguments with ``false`` or ``true`` defaults require JSON booleans, not strings.
``parameters_json`` and ``value_json`` are strings containing JSON, rather than nested JSON argument objects.
The registered tool input schema gives their types.

Tool results are text content containing reference text, YAML, diagrams or serialized JSON, as described below.
Structured operation results include status, diagnostics and phase summaries.
A tool result is not a CLI exit code or an HTTP response.
The MCP protocol can report a tool error for invalid arguments.
Unexpected tool failures are logged with value-free formatting and redacted before they reach the client.
Normal EOF or orderly shutdown ends the process; application startup failures use the shared process boundary.

SDL text is supplied as ``sdl_content``.
These authoring tools return new content rather than replacing source files.
Parsing or validation success does not establish realization or scientific reproducibility.
Reference planning uses the declared stub manifest.
Use :doc:`sdl` and :doc:`processor` for the underlying Python boundaries.

Reference and guidance tools
----------------------------

``raes_tool_surface()``
    Returns JSON describing tool families, the recommended route and safety boundaries.

``raes_agent_guidance(audience="all")``
    Returns the agent guidance profile for ``all``, ``contributor`` or ``operator`` audiences.

``raes_intended_use_profiles(profile_id="")``
    Returns the catalog or one selected profile's concerns, evidence, limitations and delivery blockers.
    It assesses system delivery capability rather than a specific scenario or run.

``sdl_overview()``
    Returns SDL reference text and a minimal example.

``sdl_section_reference(section)``
    Returns section fields, syntax, shorthands and validation rules.
    The selected name identifies an SDL section, such as ``nodes`` or ``orchestration``.

``sdl_get_example(name)``
    Returns the named SDL example: ``hospital``, ``satcom``, ``port`` or ``minimal``.
    Example coverage is not proof of backend support.

``sdl_parser_reference()``
    Returns parser, shorthand, variable and duration reference text.
    Exact syntax admission still follows the selected source profile.

``sdl_validation_reference()``
    Returns validation passes, reference resolution, diagnostic and advisory descriptions.

Authoring and experiment tools
-------------------------------

``sdl_validate(sdl_content, structural_only=false, accept_migration_syntax=false)``
    Returns success, advisories or structured parse, structural and semantic errors.
    ``structural_only`` skips semantic checks.
    Migration acceptance must be explicitly enabled.

``sdl_validate_section(section, section_yaml, context_yaml="")``
    Wraps a section in a minimal scenario and returns validation results.
    Structural validation always runs; semantic validation requires nonempty context.

``sdl_scaffold(complexity="standard", scenario_name="my-scenario", description="A new SDL scenario")``
    Returns a starter YAML document.
    Complexity accepts ``minimal``, ``standard`` or ``full``.

``sdl_instantiate(sdl_content, parameters_json="{}")``
    Returns a resolved scenario summary or instantiation errors for the supplied parameter mapping.

``experiment_validate(spec_content)``
    Validates experiment-authoring YAML and returns a summary or structured errors.
    An authored experiment specification is a pre-run design, not an admitted run.

``experiment_scaffold(complexity="minimal", spec_id="my-experiment-spec", task_ref_id="task-example-v1")``
    Returns starter experiment YAML for ``minimal``, ``sweep`` or ``variation`` complexity.

``experiment_get_example(name)``
    Returns the ``sweep``, ``smoke`` or ``variation`` experiment example.

Language service tools
----------------------

``sdl_completions(sdl_content, cursor_path="", prefix="")``
    Returns structured completion candidates for a JSON-pointer-like cursor path, with an optional prefix filter.

``sdl_references(sdl_content, symbol)``
    Returns definitions and occurrences for a bare or qualified symbol.

``sdl_format(sdl_content)``
    Returns canonical source text, recognized migration advisories and diagnostics.
    It does not write a file.

``sdl_diagnostics(sdl_content, semantic_validation=true)``
    Returns JSON diagnostic records with severity, code, stage and message.

``sdl_apply_edit(sdl_content, operation, pointer, value_json="null")``
    Returns edited content and validation diagnostics.
    Operation accepts ``set``, ``delete`` or ``append``; ``value_json`` supplies set or append values.

Inspection tools
----------------

``sdl_summarize(sdl_content)``
    Returns scenario identity, section and element counts, variables and topology summaries.

``sdl_list_elements(sdl_content, section="all")``
    Returns element names grouped by section or selected by one section name.

``sdl_get_element(sdl_content, element_name)``
    Returns a bare or qualified element's fields, references and related context.

``sdl_check_references(sdl_content, element_name="")``
    Returns incoming and outgoing references for one element, or a full graph summary when the name is empty.

``sdl_diagram(sdl_content)``
    Returns an ASCII network topology diagram.
    It describes authored structure rather than observed deployment.

Processing and assessment tools
--------------------------------

``sdl_parse(sdl_content, semantic_validation=false, accept_migration_syntax=false)``
    Returns JSON describing normalized shape, populated sections, advisories and optional semantic-validation status.

``sdl_compile(sdl_content, parameters_json="{}", accept_migration_syntax=false)``
    Returns JSON domain counts, participant-contract counts, migration advisories and compiler diagnostics.

``sdl_plan(sdl_content, parameters_json="{}")``
    Returns JSON resource and operation counts, capability diagnostics and the reference stub manifest identity.
    It does not apply the plan.

``raes_reference_manifests()``
    Returns JSON summaries of the reference processor and stub backend manifests.

``sdl_design_assessment(sdl_content, parameters_json="{}")``
    Returns stage status, design notes, diagnostics and next-step guidance through reference planning.

``sdl_claims_assessment(sdl_content, parameters_json="{}")``
    Returns supported, conditional and unsupported claims, with missing evidence and provenance requirements.
    It does not create that evidence.

Server construction
-------------------

``raes_mcp.server.create_server()`` returns the configured FastMCP server without starting its transport.
It registers the 31 tools listed above.
``raes_mcp.server.main()`` configures operational logging and runs the stdio server through the shared application boundary.
The console entry point selects this function.
