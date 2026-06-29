# Ensures the project root is importable when pytest is invoked as bare `pytest`
# (CI runs `pytest`, which — unlike `python -m pytest` — does not add the repo root
# to sys.path). pytest imports this file before collecting tests, so the insert
# below makes `import analytics`, `import ingest`, etc. resolve in every environment.
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
