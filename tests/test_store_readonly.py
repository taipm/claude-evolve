"""store_dir must not raise when the project root is read-only (e.g. cwd=/)."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import store

os.environ["CLAUDE_PROJECT_DIR"] = "/"
d = store.ensure_store()
assert d.is_dir() and d.parts[:2] != ("/", ".claude"), d
print("ok", d)
