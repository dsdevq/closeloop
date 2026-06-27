"""Parse an uploaded XLSX file into a list of raw row dicts."""

from io import BytesIO

import openpyxl


def parse_xlsx(file_bytes: bytes) -> list[dict]:
    """Load *file_bytes* as an XLSX workbook and return one dict per data row.

    The first row of the active worksheet is treated as the header; its cell
    values become the keys of each returned dict, exactly as they appear (no
    transformation applied).  An empty file or a sheet with no data rows
    returns [].
    """
    wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []

    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]
