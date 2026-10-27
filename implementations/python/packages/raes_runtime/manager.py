"""Compatibility entry point for the single runtime lifetime owner."""

from .control_plane import RuntimeControlPlane
from .interaction import _RuntimeApplyState as _RuntimeApplyState

RuntimeManager = RuntimeControlPlane

__all__ = ["RuntimeManager"]
