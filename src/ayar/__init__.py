"""ayar: assay your spike-sorted finding before you publish.

ayar reads the output of any spike sorter, flags sorting artifacts that can
manufacture or hide a result (duplicated and split units, contamination, overlap
holes, drift-driven rate changes), re-computes *your* finding with the flagged
units repaired, and tests whether it depends on curation thresholds or on the
choice of spike sorter.

    import ayar
    bundle = ayar.load("kilosort_output/")          # or a .npz bundle
    report = ayar.scan(bundle, finding=my_analysis)
    print(report)
"""

__version__ = "0.4.0"

from .bundle import Bundle, Events  # noqa: E402
from .config import DEFAULTS, Thresholds  # noqa: E402
from .flags import Flag, NotChecked, Report, Severity  # noqa: E402
from .io import from_alf, from_arrays, from_ibl, from_nwb, from_phy, from_spikeinterface, load  # noqa: E402
from .compare import compare  # noqa: E402
from .matching import match_units  # noqa: E402
from .multiverse import Rule, multiverse  # noqa: E402
from .scan import scan  # noqa: E402
from .synth import SynthConfig, make_session  # noqa: E402
from .validate import validate  # noqa: E402

__all__ = [
    "Bundle", "Events", "Thresholds", "DEFAULTS", "Flag", "NotChecked", "Report", "Severity",
    "from_arrays", "from_phy", "from_ibl", "from_alf", "from_spikeinterface", "from_nwb", "load", "scan", "multiverse",
    "Rule", "compare", "match_units", "make_session", "SynthConfig", "validate",
    "__version__",
]
