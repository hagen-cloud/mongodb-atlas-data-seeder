"""Safety checks to avoid running against the wrong cluster.

The seeder writes large volumes of throwaway data, so it must never touch a
production cluster. Two independent checks are enforced before any write:
  1. the connection URI must not contain any blocklisted (prod) token, and
  2. the configured ``env`` must match ``safety.require_env``.
"""

from __future__ import annotations

import os

from .config import Config


class GuardrailError(RuntimeError):
    """Raised when a safety check fails. The process must abort."""


def check(cfg: Config) -> str:
    """Enforce the safety checks and return the validated URI, or raise.

    Raises ``GuardrailError`` if the URI is unset, matches a prod blocklist
    token, or the configured env does not match ``safety.require_env``.
    """
    uri = os.environ.get(cfg.connection.uri_env, "")
    if not uri:
        raise GuardrailError(
            f"Connection URI env '{cfg.connection.uri_env}' is not set"
        )

    lowered = uri.lower()
    for token in cfg.safety.prod_host_blocklist:
        if token and token.lower() in lowered:
            raise GuardrailError(
                f"Refusing to run: URI matches prod blocklist token '{token}'"
            )

    required = (cfg.safety.require_env or "").strip()
    if required and cfg.env.strip().lower() != required.lower():
        raise GuardrailError(
            f"Refusing to run: env='{cfg.env}' does not match required '{required}'"
        )

    return uri
