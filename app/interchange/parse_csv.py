"""Parse an uploaded CSV file into a list of raw row dicts."""

import csv
import io


def parse_csv(file_bytes: bytes) -> list[dict]:
    """Decode *file_bytes* as UTF-8 and return one dict per data row.

    Keys in each dict are the header names exactly as they appear in the file
    (no normalisation or transformation applied).  An empty file returns [].
    """
    text = file_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    # DictReader yields nothing when the source is empty or header-only with
    # no data rows; list() handles both cases correctly.
    return list(reader)
