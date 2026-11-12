# SDL variation-points/v1 fixtures

This reference describes the SCE-002 family corpus.
The `valid` folder contains valid bounded families.
The `invalid` folder contains a dangling member reference.
The `composition` folder tests exported and private names after import.
The `canonical` folder tests equal bytes for absent and empty point maps.

`valid/node-inventory.yaml` declares node presence and coupled inventory choices.
Its choices preserve the family and select existing job records.
The absent choice also removes the worker's deployment entry.

`valid/dependent-declarations.yaml` couples node absence with dependent declarations.
The absent choice also removes the node's account and its shared volume mount.
The sensor keeps its mount on the shared volume.

The [variation-point reference](../../../../specs/sdl/variation-points.md)
defines the authoring rules.
`test_sdl_variation_points.py` checks the base corpus.
`test_issue_1625_structural_variation.py` checks node inventory choices.
`test_issue_1733_dependent_declaration_variation.py` checks dependent declarations.
These cases do not establish backend realization of every family member.
