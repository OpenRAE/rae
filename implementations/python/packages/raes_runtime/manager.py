"""Compatibility entry point for the single runtime lifetime owner."""

from . import interaction as _interaction
from .control_plane import RuntimeControlPlane

RuntimeManager = RuntimeControlPlane
_RuntimeApplyState = _interaction._RuntimeApplyState

__all__ = ["RuntimeManager"]
