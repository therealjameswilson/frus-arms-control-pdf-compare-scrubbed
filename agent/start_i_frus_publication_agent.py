#!/usr/bin/env python3
"""Backward-compatible START I command for the universal FRUS agent."""

from __future__ import annotations

from frus_publication_agent import main


if __name__ == "__main__":
    raise SystemExit(main())
