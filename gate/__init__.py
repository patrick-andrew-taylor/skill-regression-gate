"""Skill regression gate — a zero-dependency harness for grading agent skills."""

__version__ = "1.1.0"

# Recorded into every cassette so a transcript can always be traced back to the
# harness that produced it. Cassettes written before provenance existed report
# "unknown" at replay rather than being silently assumed current.
HARNESS_VERSION = __version__
