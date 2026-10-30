"""ayar: assay your spike-sorted finding before you publish.

ayar reads the output of any spike sorter, flags sorting artifacts that can
manufacture or hide a result (duplicated units, overlap holes, drift-driven rate
changes), and re-computes *your* finding without the flagged units to tell you
whether it survives.

    import ayar
    bundle = ayar.load("kilosort_output/")          # or a .npz bundle
    report = ayar.scan(bundle, finding=my_analysis)
    print(report)
"""

__version__ = "0.1.0"

from .bundle import Bundle, Events  # noqa: E402
from .config import DEFAULTS, Thresholds  # noqa: E402
from .flags import Flag, NotChecked, Report, Severity  # noqa: E402
from .io import from_arrays, from_phy, load  # noqa: E402
from .scan import scan  # noqa: E402
from .synth import SynthConfig, make_session  # noqa: E402
from .validate import validate  # noqa: E402

__all__ = [
    "Bundle", "Events", "Thresholds", "DEFAULTS", "Flag", "NotChecked", "Report", "Severity",
    "from_arrays", "from_phy", "load", "scan", "make_session", "SynthConfig", "validate",
    "__version__",
]
