#!/usr/bin/env python3
"""GitHub Contribution Analyzer Bot - Main application module."""

import asyncio

from .app import main

if __name__ == "__main__":
    asyncio.run(main())
