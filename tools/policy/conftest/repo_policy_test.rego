package main

import rego.v1


test_legacy_root_is_blocked if {
  failures := deny with input as {
    "changed": ["schemas/backend-manifest.json"],
    "check_set": "file-local",
    "policy": {
      "legacy_top_level_roots": ["schemas"],
      "concept_authority": {"reserved_path_tokens": [], "allowed_paths": []},
      "source_roots": [],
      "changelog_path": "CHANGELOG.md",
      "changelog_fragment_dir": "changelog.d",
    },
  }
  count(failures) == 1
  some failure in failures
  failure.rule_id == "legacy-top-level-root"
}


test_reserved_concept_authority_paths_are_enforced if {
  failures := deny with input as {
    "changed": ["docs/drafts/concept-authority-notes.md"],
    "check_set": "file-local",
    "policy": {
      "legacy_top_level_roots": [],
      "concept_authority": {
        "reserved_path_tokens": ["concept-authority"],
        "allowed_paths": ["docs/explain/reference/shared-concept-model.md"],
      },
      "source_roots": [],
      "changelog_path": "CHANGELOG.md",
      "changelog_fragment_dir": "changelog.d",
    },
  }
  count(failures) == 1
  some failure in failures
  failure.rule_id == "concept-authority-reserved-path"
}


test_concept_authority_schema_publication_record_is_allowed if {
  failures := deny with input as {
    "changed": ["contracts/schema-publication/entries/concept-families-v1.json"],
    "check_set": "file-local",
    "policy": {
      "legacy_top_level_roots": [],
      "concept_authority": {
        "reserved_path_tokens": ["concept-authority", "concept-families-v1"],
        "allowed_paths": ["contracts/schema-publication"],
      },
      "source_roots": [],
      "changelog_path": "CHANGELOG.md",
      "changelog_fragment_dir": "changelog.d",
    },
  }
  count(failures) == 0
}
