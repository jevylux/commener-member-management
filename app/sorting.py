"""Sorting utilities for Flask list views."""
import unicodedata

ASC = 'asc'
DESC = 'desc'


def normalise(value):
    """Normalise a string for case-insensitive sorting."""
    if value is None:
        return ''
    return unicodedata.normalize('NFKD', str(value)).lower()


def parse_sort(sort_param, allowed_columns, default='id'):
    """Parse a sort parameter string into (column, direction).
    
    Args:
        sort_param: The sort query parameter (e.g. 'name', '-name')
        allowed_columns: Tuple of valid column names
        default: Default column if sort_param is empty or invalid
    
    Returns:
        (sort_key, sort_direction) where direction is ASC or DESC
    """
    if not sort_param:
        return default, ASC
    
    if sort_param.startswith('-'):
        direction = DESC
        key = sort_param[1:]
    else:
        direction = ASC
        key = sort_param
    
    if key not in allowed_columns:
        return default, ASC
    
    return key, direction


def sort_rows(items, sort_key, sort_dir, key_map):
    """Sort a list of items based on a key map.
    
    Args:
        items: Iterable of items to sort
        sort_key: The column key to sort by
        sort_dir: ASC or DESC
        key_map: Dict mapping column names to lambda functions that extract sort keys
    
    Returns:
        Sorted list of items
    """
    if sort_key not in key_map:
        return list(items)
    
    reverse = sort_dir == DESC
    sorted_items = sorted(items, key=key_map[sort_key], reverse=reverse)
    return sorted_items


def sort_target(endpoint, column, current_key, current_dir):
    """Generate a sort query parameter for a column header link.
    
    Args:
        endpoint: The endpoint (kept for template compatibility)
        column: The column being clicked
        current_key: Current sort key
        current_dir: Current sort direction
    
    Returns:
        Sort parameter string (e.g. 'name' or '-name')
    """
    if current_key == column and current_dir == ASC:
        return f'-{column}'
    return column


def sort_indicator(column, current_key, current_dir):
    """Return a sort indicator string for display in column headers.
    
    Args:
        column: The column to check
        current_key: Current sort key
        current_dir: Current sort direction
    
    Returns:
        ' ▲' if ascending, ' ▼' if descending, '' if not sorted
    """
    if current_key != column:
        return ''
    if current_dir == DESC:
        return ' ▼'
    return ' ▲'
