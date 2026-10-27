"""TradeLab V4: offline research and read-only historical market data."""
import sys
from pathlib import Path
_VENDOR = Path(__file__).parent / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
__version__ = "4.0.0"

