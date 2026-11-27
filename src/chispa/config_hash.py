"""The hash of the values of `config.py` that can change a result.

The stamp of each result table has this hash, and the mark of the saved trees of the live
growth forecast has it also. Thus it is not in the evaluation: the live path uses it, and that
path imports no module of the evaluation.
"""

import hashlib
from pathlib import Path

from chispa import config

# The start of the marker line in `config.py`. The hash covers the text before it.
HASH_END = "# === The values above this line can change a result."


def config_hash() -> str:
    """Return a short hash of the first part of `config.py`: the values that can change a result.

    Two runs with the same hash used the same settings. A new path or a new live value
    is below the marker line, thus it does not change the hash of a frozen evaluation.
    """
    text = Path(config.__file__).read_text()
    if HASH_END not in text:
        raise RuntimeError("config.py has no marker line. Put the line back, then run again.")
    return hashlib.sha256(text.split(HASH_END)[0].encode()).hexdigest()[:12]
