"""Public access to frozen, version-independent canonical measurement primitives.

V1 remains byte-for-byte frozen. These small pure helpers preserve its exact
geometry, window fitness and owner conventions; descriptive versioning lives in
the sibling producers. Consumers do not depend on a V2 private family or gate.
"""
from contextual_technical_features import (
    morphology, _number as finite_number, _ohlc_valid as valid_ohlc,
    _signature as series_signature, _gate as canonical_window_fitness,
    _true_range as true_range, _distribution as distribution,
    _bar_units as bar_units, _level as level_observation,
    _pattern_labels as morphology_labels,
)

USABLE = frozenset({"AVAILABLE", "DESCRIPTIVE_ONLY"})
