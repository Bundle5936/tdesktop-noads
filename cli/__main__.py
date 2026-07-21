from pathlib import Path
import sys

# Allow: python -m cli  (from repo root) or python cli/__main__.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tdesktop_noads import main

raise SystemExit(main())
