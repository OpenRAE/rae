"""Container-image trust policy for the reference OCI driver."""

from __future__ import annotations

import re
from dataclasses import dataclass

# OCI/distribution reference grammar, restricted to the trust boundary's needs.
# The name is an optional ``registry[:port]`` domain plus one or more lowercase
# path components; character classes for separators and alphanumerics are
# disjoint, so matching is linear (no catastrophic backtracking).
_REF_DOMAIN_COMPONENT = r"(?:[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9])"
# Docker and containerd also accept a bracketed IPv6 authority (``[2001:db8::1]``,
# optionally with a port), so a registry reachable only over IPv6 must not be
# rejected. Bounded and built from a disjoint character class, so still linear.
_REF_IPV6_AUTHORITY = r"\[[0-9A-Fa-f:.]{2,45}\]"
_REF_DOMAIN = rf"(?:{_REF_DOMAIN_COMPONENT}(?:\.{_REF_DOMAIN_COMPONENT})*|{_REF_IPV6_AUTHORITY})(?::[0-9]+)?"
_REF_PATH_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*"
_REF_NAME = rf"(?:{_REF_DOMAIN}/)?{_REF_PATH_COMPONENT}(?:/{_REF_PATH_COMPONENT})*"
_REF_TAG = r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}"

# A digest-pinned reference is the driver's trust anchor: the content is bound
# to a specific manifest digest a plan author cannot swap. It is accepted only
# when a well-formed name (with optional tag) is terminated by a canonical
# ``sha256:`` digest of exactly 64 lowercase hex characters. ``fullmatch`` keeps
# the digest anchored at the very end, so an unanchored ``@sha256:`` substring
# that never actually pins content -- ``evil/img@sha256:x/pull-me:latest``,
# ``foo@sha256:short`` -- is rejected rather than trusted.
_DIGEST_PINNED_REF = re.compile(rf"{_REF_NAME}(?::{_REF_TAG})?@sha256:[0-9a-f]{{64}}")
_NAMED_REF = re.compile(rf"{_REF_NAME}(?::{_REF_TAG})?")


def is_image_reference(image: str) -> bool:
    """Admit only image names, never URLs, credentials, or CLI options."""

    return (
        isinstance(image, str)
        and len(image) <= 512
        and (_NAMED_REF.fullmatch(image) is not None or _DIGEST_PINNED_REF.fullmatch(image) is not None)
    )


# The interpreter synthesizes ``raes-reference/<os-family>`` (or
# ``raes-reference/base``) for a node that pins no image source. Match that
# exact placeholder shape -- a single lowercase path component -- so a
# ``default_image`` substitution can never be triggered by a plan-author ref
# that merely starts with the prefix while smuggling extra ``/``, ``:``, or
# ``@`` structure past it.
_PLACEHOLDER_REF = re.compile(rf"raes-reference/{_REF_PATH_COMPONENT}")


@dataclass(frozen=True)
class ImageTrustPolicy:
    """Operator policy deciding which container images may be realized.

    A plan author controls ``spec.image_ref`` (via ``node.source``) and ``run``
    pulls+executes it; fixed argv stops shell injection but is not an image
    trust boundary. Only the operator ``default_image``, an explicit
    ``allowed_images`` entry, or a digest-pinned ref (``...@sha256:...``) is
    permitted, so plan submission cannot become arbitrary-image code execution.
    """

    default_image: str | None = None
    allowed_images: tuple[str, ...] = ()
    allow_digest_pinned: bool = True

    def image_for(self, image_ref: str) -> str:
        # A configured default overrides the synthesized ``raes-reference/*``
        # placeholder so an image-less plan can still realize against a registry.
        if self.default_image and _PLACEHOLDER_REF.fullmatch(image_ref):
            return self.default_image
        return image_ref

    def permits(self, image: str) -> bool:
        if not is_image_reference(image):
            return False
        return (
            (self.default_image is not None and image == self.default_image)
            or image in self.allowed_images
            or (self.allow_digest_pinned and _DIGEST_PINNED_REF.fullmatch(image) is not None)
        )


__all__ = ["ImageTrustPolicy", "is_image_reference"]
