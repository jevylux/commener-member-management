"""Helpers for server-side sorting of list pages.

Sorting is driven by two query string parameters:

    ?sort=<column_key>&dir=<asc|desc>

Both are validated against a whitelist supplied by the view, so a
malformed or hostile query string can never reach an arbitrary SQL
expression. Sorting itself happens in Python on the already-loaded
result set: the member and pod tables are small (tens of rows), and
doing it here gives us a single, accent- and case-insensitive
comparison rule instead of relying on SQLite's BINARY collation,
which sorts accented names after 'z' ("Delleré" would land after
"Diderrich").
"""

import unicodedata

from flask import request, url_for

ASC = 'asc'
DESC = 'desc'


def normalise(value):
    """Return a case- and accent-insensitive comparison key for `value`.

    "Véronique" -> "veronique", "Delleré" -> "deller".

    Surrounding whitespace is stripped as well: some records carry a
    trailing space ("Sebastian "), which would otherwise sort after
    "Sebastian" instead of next to it.
    """
    if value is None:
        return ''
    decomposed = unicodedata.normalize('NFKD', str(value))
    stripped = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold().strip()


def parse_sort(default_key, allowed):
    """Read and validate the `sort` / `dir` query string parameters.

    `allowed` is an iterable of valid column keys. Unknown values fall
    back to `default_key` and to ascending order.
    """
    sort_key = request.args.get('sort', default_key)
    if sort_key not in allowed:
        sort_key = default_key

    direction = request.args.get('dir', ASC).lower()
    if direction not in (ASC, DESC):
        direction = ASC

    return sort_key, direction


def sort_rows(rows, key_map, sort_key, direction):
    """Sort `rows` using the key function registered under `sort_key`.

    `key_map` maps a column key to a callable returning a tuple
    `(is_missing, sort_values)` for one row:

    * `is_missing` - True when the row has no value for the column.
    * `sort_values` - the tuple the row is compared by.

    Rows with a missing value are kept at the bottom in both
    directions. A plain `sorted(..., reverse=True)` would move them to
    the top when sorting descending, which is not what a user expects.

    The sort is stable, so rows that compare equal keep their original
    database order.
    """
    key_func = key_map.get(sort_key)
    if key_func is None:
        return rows

    populated = []
    empty = []
    for row in rows:
        is_missing, values = key_func(row)
        (empty if is_missing else populated).append((row, values))

    populated.sort(key=lambda pair: pair[1], reverse=(direction == DESC))
    return [row for row, _ in populated] + [row for row, _ in empty]


def sort_target(endpoint, column, current_key, current_dir):
    """Return the query string that toggles sorting on `column`.

    Clicking the column that is already sorted flips the direction;
    clicking another column starts over in ascending order.
    """
    if column == current_key:
        next_direction = DESC if current_dir == ASC else ASC
    else:
        next_direction = ASC

    args = {key: value for key, value in request.args.items()}
    args['sort'] = column
    args['dir'] = next_direction
    return url_for(endpoint, **args)


def sort_indicator(column, current_key, current_dir):
    """Return the arrow shown next to the active column header."""
    if column != current_key:
        return ''
    return ' ▲' if current_dir == ASC else ' ▼'
