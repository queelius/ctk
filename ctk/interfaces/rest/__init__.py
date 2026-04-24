"""RESTful API interface for CTK.

``RestInterface`` is imported lazily so adjacent submodules
(e.g., ``_validation``) can be imported without requiring Flask.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .api import RestInterface  # noqa: F401

__all__ = ["RestInterface"]


def __getattr__(name):
    if name == "RestInterface":
        from .api import RestInterface

        return RestInterface
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
