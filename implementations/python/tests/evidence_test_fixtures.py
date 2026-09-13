"""Cache committed evidence reads while giving each test an isolated copy."""

from copy import deepcopy
from functools import cache


@cache
def _committed_bundle(loader, root):
    return loader(root)


def copy_bundle(loader, root):
    return deepcopy(_committed_bundle(loader, root))
