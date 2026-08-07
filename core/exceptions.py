# -*- coding: utf-8 -*-
"""Typed exception hierarchy.

Workers map these onto their signal contract (cancelled / dep_missing /
failed); services and core raise them instead of returning sentinel values.
"""


class BFIError(Exception):
    """Base class for all Best Fit Interpolator errors."""


class DependencyMissing(BFIError):
    """An optional Python package is not importable."""

    def __init__(self, package: str):
        self.package = package
        super().__init__(package)

    def user_message(self) -> str:
        return (
            "This feature requires the Python package '{}'.\n"
            "The plugin installs it automatically on startup when an internet "
            "connection is available; use 'Retry dependency installation' in "
            "the About tab if it is still missing."
        ).format(self.package)


class OperationCancelled(BFIError):
    """The user cancelled a running computation."""


class InsufficientSamples(BFIError):
    """Too few valid samples for the requested method."""

    def __init__(self, method_label: str, needed: int, got: int):
        self.method_label = method_label
        self.needed = needed
        self.got = got
        super().__init__(
            f"{method_label} needs at least {needed} valid samples; got {got}."
        )


class InvalidDataError(BFIError):
    """Input data cannot be used (duplicate coordinates, non-finite values,
    empty extent, CRS mismatch, ...)."""


class ComputationError(BFIError):
    """A numerical routine failed (singular kriging system, variogram fit
    did not converge, ...)."""
