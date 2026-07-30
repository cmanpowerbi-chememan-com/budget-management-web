"""conftest for tests_data_sync — make the `app` package importable when this
directory is collected on its own (it sits OUTSIDE backend/tests/, so that
directory's conftest does not apply here)."""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
