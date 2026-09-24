"""Writing expected provenance in watts.

``sink_adapters_source_shares`` — the *provenance map* — says, for every
device drawing power (a *sink*), which fraction of its draw came from each
device supplying power (a *source*): ``{sink: {source: share}}``. One sink's
entry is its *row*; a row sums to 1, or is all zeros when nothing it may use
is supplying.

By hand those answers are worked out in watts, not fractions, so the
harnesses write them that way and let :func:`rows` do the division. A row
lists every source supplying in the snapshot, zeros included.
"""

from __future__ import annotations

from fractions import Fraction as F


def rows(watts: dict[str, dict[str, int | F]]) -> dict[str, dict[str, F]]:
    """A ``{sink: {source: watts}}`` table as the provenance rows it implies.

    A row with no watts at all — a sink with nothing it may draw from — is a
    row of zeros, not a division by zero.
    """
    out = {}
    for sink, row in watts.items():
        total = sum(row.values())
        out[sink] = {src: F(w) / total if total else F(0) for src, w in row.items()}
    return out
