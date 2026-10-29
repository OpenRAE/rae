"""SDL-to-runtime compiler.

Public facade for the compiler package. The compilation logic is split across
package-private submodules (foundations -> domain compilers -> pipeline); this
module re-exports the stable public API so ``raes_processor.compiler`` keeps its
external contract.
"""

from ._mixed_control_policy import project_control_episode_policy
from .materialization_origins import materialization_differences, validate_materialization_origins
from .pipeline import compile_runtime_model, compile_scenario_runtime_model

__all__ = [
    "compile_runtime_model",
    "compile_scenario_runtime_model",
    "materialization_differences",
    "validate_materialization_origins",
    "project_control_episode_policy",
]
