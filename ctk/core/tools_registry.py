"""
Tool provider registry for LLM tool calling.

This module holds the provider-agnostic machinery that callers use to
discover the tools available to an LLM. As of 2.12.0 the ctk model is
"everything the LLM can do is a tool, and every tool comes from a named
provider" (modeled like an MCP server).

Tool *definitions* no longer live here: the built-in tools are defined in
``ctk.core.builtin_tools`` (which registers the ``ctk.builtin`` provider on
import), and the network-analysis tools live in ``ctk.core.network_tools``
(``ctk.network``). Future external MCP servers register through this same
``register_provider`` interface, so ``/mcp`` inside the TUI shows everything
in one list.

Providers are intentionally tiny -- just a name, description, and a list of
tool dicts. ``available`` is reserved for the day a provider's upstream is
unreachable (e.g. an MCP server that's down); built-in providers are always
available.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ToolProvider:
    """A named source of LLM tools, modeled like an MCP server."""

    name: str
    description: str = ""
    tools: List[Dict[str, Any]] = field(default_factory=list)
    available: bool = True


# The registry is a module-global list. Providers append themselves when
# their defining module is imported: ``ctk.builtin`` from
# ``ctk.core.builtin_tools`` and ``ctk.network`` from
# ``ctk.core.network_tools``. ``ctk/tui/app.py:_register_builtin_providers``
# imports those modules before the TUI mounts.
_PROVIDERS: List[ToolProvider] = []


def register_provider(provider: ToolProvider) -> None:
    """Append a provider to the registry.

    Idempotent on name: if a provider with the same name already
    exists, replace it (so re-importing a tools module during dev
    doesn't accumulate duplicates).
    """
    for i, existing in enumerate(_PROVIDERS):
        if existing.name == provider.name:
            _PROVIDERS[i] = provider
            return
    _PROVIDERS.append(provider)


def iter_providers() -> Iterable[ToolProvider]:
    """Iterate over all registered tool providers in display order."""
    return list(_PROVIDERS)


def provider_for_tool(name: str) -> Optional[str]:
    """Return the name of the provider that owns ``name``, or None.

    Routing derives from provider ownership rather than a hardcoded
    name set, so adding a tool to a provider needs no edit elsewhere.
    """
    for provider in _PROVIDERS:
        for tool in provider.tools:
            if tool.get("name") == name:
                return provider.name
    return None


def all_tools() -> List[Dict[str, Any]]:
    """Flat list of every tool from every available provider.

    Used by callers (the TUI worker, MCP server) that want one list to
    hand to an LLM. Unavailable providers are skipped so the model
    isn't told about tools that will fail to execute.
    """
    out: List[Dict[str, Any]] = []
    for provider in _PROVIDERS:
        if provider.available:
            out.extend(provider.tools)
    return out
