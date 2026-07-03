import time
from typing import Any


def makeResult(success: bool, output: Any = None, error: str | None = None, startTime: float | None = None) -> dict:
    """Return the standard ScriptResult envelope."""
    elapsed = round(time.time() - startTime, 3) if startTime is not None else 0.0
    return {"success": success, "output": output, "error": error, "elapsed_s": elapsed}
