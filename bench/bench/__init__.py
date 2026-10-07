"""The M0 benchmark harness (#12): times the AI pipeline against a running stack."""

# DSPy 3.4 swaps NumPy for a lazy module when it is imported first, and a later
# `import numpy.typing` then fails. Importing NumPy before anything else avoids it.
import numpy  # noqa: F401

METHOD_VERSION = 1
"""Recorded in every results file. Bump it when a change makes new results incomparable with
earlier ones, such as a different prompt or a different way of measuring."""
