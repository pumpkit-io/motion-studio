"""motion-studio: an agent-driven video editing harness."""

from importlib.metadata import version

# The one place the product name lives in code; see docs/renaming.md.
APP_NAME = "motion-studio"
ENV_PREFIX = APP_NAME.upper().replace("-", "_")

__version__ = version(APP_NAME)
