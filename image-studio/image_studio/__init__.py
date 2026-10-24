"""Image Studio - analyse, enhance and unify photos so a whole set looks like one shoot."""
from .analyze import consistency
from .config import list_presets, load_preset
from .pipeline import Result, analyze, process

__version__ = "0.1.0"
__all__ = ["Result", "analyze", "consistency", "list_presets", "load_preset", "process", "__version__"]
