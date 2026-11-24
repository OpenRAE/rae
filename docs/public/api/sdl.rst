SDL authoring layer
===================

The ``raes`` package owns authoring models, parsing, validation and instantiation.
It does not provision a backend or start a runtime.
Use the :doc:`Python task guide <../guides/python>` for procedures.

Input and result boundaries
---------------------------

``parse_sdl(content, path=None)`` accepts YAML text.
It uses ``sdl-yaml/v1``, rejects legacy syntax by default and runs semantic validation.
``skip_semantic_validation=True`` skips semantic checks for authoring input only.
Materialized roots always undergo semantic admission.
Structural admission always runs.
``path`` supplies source context and the base for file-backed imports.
Those imports can read files, consult trust settings and acquire OCI modules.

``parse_sdl_file(path, **kwargs)`` reads bounded UTF-8 bytes and forwards options to ``parse_sdl``.
Missing files raise ``FileNotFoundError``; other file access failures can raise ``OSError``.
``parse_sdl_sources(sources, root)`` instead reads only the supplied path-to-bytes mapping.
It never reads the filesystem, environment or network.
Imported local sources require exact lock records and digest pins.

The result is ``Scenario`` or ``ExpandedScenario`` for authoring input.
The file and text entry points also admit ``MaterializedScenario`` descriptions.
The supplied-source entry point refuses a materialized root.
Parsing and structural failures raise ``SDLParseError``.
Semantic failures raise ``SDLValidationError``.
Import failures raise ``SDLImportError`` with an ``SDLImportErrorCode``.
Source positions are one-based; ranges are half-open.

``instantiate_scenario`` binds declared variables and the selected profile.
It returns an admitted ``InstantiatedScenario`` or raises ``SDLInstantiationError``.
Canonical byte and digest functions require the corresponding validated scenario type.
They do not read or write files.
Materialized descriptions use their own identity profile rather than an executable snapshot profile.

``format_sdl_source`` and ``render_sdl_source`` return typed content and diagnostics.
They do not replace a file themselves.
Rename and removal operations return transformation reports with preservation checks and losses.
Candidate synthesis returns candidates and diagnostics, not proof of a realizable scenario.

Default parser limits
---------------------

``SDLParserLimits`` supplies these defaults.
Callers can pass another instance through ``limits``.

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - Limit
     - Default
   * - Input / scalar bytes
     - 8,388,608 / 1,048,576
   * - Source depth / nodes / aliases
     - 128 / 100,000 / 256
   * - Expanded nodes / imports
     - 250,000 / 256
   * - Composed nodes / bytes
     - 500,000 / 33,554,432
   * - Composition / namespace depth
     - 32 / 32

.. currentmodule:: raes

Public API
----------

.. automodule:: raes
   :members:
   :exclude-members: admit_instantiated_scenario,
      admit_materialized_scenario,
      admit_scenario_family,
      MaterializedScenario,
      canonical_materialized_sdl_bytes,
      canonical_materialized_sdl_digest,
      canonical_instantiated_sdl_bytes,
      canonical_instantiated_sdl_digest,
      canonical_sdl_bytes,
      canonical_sdl_digest,
      ExpandedScenarioBindingTargetResolver,
      instantiate_scenario,
      InstantiatedScenario,
      InstantiatedScenarioSnapshot,
      SDLCanonicalDigest,
      load_sdl_fragment,
      parse_sdl,
      parse_sdl_file,
      parse_sdl_sources,
      ArtifactTransformationPolicy,
      CanonicalArtifactComparison,
      PortableContractTransformationResult,
      RemoveSDLDeclarationRequest,
      RenameSDLDeclarationRequest,
      canonicalize_portable_contract,
      compare_canonical_artifacts,
      remove_sdl_declaration,
      rename_sdl_declaration,
      SDLTransformationResult,
      SDLCandidateSynthesisResult,
      synthesize_sdl_candidate,
      select_scenario_family,
      Scenario
   :imported-members:
   :undoc-members:

``__version__`` comes from installed distribution metadata.
Its fallback is ``0.0.0+unknown`` when the distribution is absent.
``VARIABLE_TOKEN_PATTERN`` is the exported variable-token pattern.
The source and canonical profile constants name separate versioned formats.

Parser
------

.. automodule:: raes.parser
   :members:

Scenario model
--------------

.. automodule:: raes.scenario
   :members:

Instantiation
-------------

.. automodule:: raes.instantiate
   :members:

Validator
---------

.. automodule:: raes.validator
   :members:

Language service
----------------

.. automodule:: raes.language_service
   :members:

Agent guidance
--------------

.. automodule:: raes.agent_guidance
   :members:

Composition
-----------

.. automodule:: raes.composition
   :members:
   :imported-members:

Artifact transformations
------------------------

.. automodule:: raes.transformations
   :members:
   :imported-members:

Module registry
---------------

.. automodule:: raes.module_registry
   :members:

Canonical identities and candidate synthesis
--------------------------------------------

.. automodule:: raes.canonical
   :members:

.. automodule:: raes.candidate_synthesis
   :members:

Family and materialization admission
------------------------------------

.. automodule:: raes.family_admission
   :members:

.. automodule:: raes.selected_scenario
   :members:
   :exclude-members: SDLSelectionError

.. automodule:: raes.materialization
   :members:

SDL models
----------

Nodes
~~~~~

.. automodule:: raes.nodes
   :members:

Infrastructure
~~~~~~~~~~~~~~

.. automodule:: raes.infrastructure
   :members:

Features
~~~~~~~~

.. automodule:: raes.features
   :members:

Vulnerabilities
~~~~~~~~~~~~~~~

.. automodule:: raes.vulnerabilities
   :members:

Relationships
~~~~~~~~~~~~~

.. automodule:: raes.relationships
   :members:

Accounts
~~~~~~~~

.. automodule:: raes.accounts
   :members:

Agents
~~~~~~

.. automodule:: raes.agents
   :members:

Content
~~~~~~~

.. automodule:: raes.content
   :members:

Entities
~~~~~~~~

.. automodule:: raes.entities
   :members:

Conditions
~~~~~~~~~~

.. automodule:: raes.conditions
   :members:

Orchestration
~~~~~~~~~~~~~

.. automodule:: raes.orchestration
   :members:
   :imported-members:

Objectives
~~~~~~~~~~

.. automodule:: raes.objectives
   :members:

Variables
~~~~~~~~~

.. automodule:: raes.variables
   :members:

Constants and type aliases
--------------------------

These entries retain the exported values and type definitions.
Version constants identify data formats, not the installed package version.
Type aliases give accepted shapes; they do not create another wire contract.
Literal values and callback types need no separate model narrative.

.. autodata:: raes.MATERIALIZED_SDL_PROFILE

.. autodata:: raes.__version__

.. autodata:: raes.INSTANTIATED_SNAPSHOT_PROFILE

.. autodata:: raes.SDL_CANONICAL_PROFILE

.. autodata:: raes.SDL_SOURCE_FORMAT

.. autodata:: raes.VARIABLE_TOKEN_PATTERN
