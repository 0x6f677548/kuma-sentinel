"""Utility functions for CLI parsing and validation."""

from typing import List, Optional, Tuple


def parse_comma_separated_tuple(
    value: str, value_type: type = int, required: bool = True
) -> Tuple[str, Optional[int]]:
    """Parse a comma-separated tuple value.

    Handles formats like:
    - Simple paths: "path,24" -> ("path", 24)
    - SSH paths: "root@fileserver:/mnt/shares,24" -> ("root@fileserver:/mnt/shares", 24)
    - Path only (when not required): "path" -> ("path", None)

    Args:
        value: String in format "first_part,second_part" or just "first_part"
        value_type: Type to convert the second part to (default: int)
        required: If True, second part must be present. If False, allows "first_part" only.

    Returns:
        Tuple of (first_part: str, second_part: converted_type or None)

    Raises:
        ValueError: If format is invalid or conversion fails
    """
    # Split on the last comma to handle paths with special characters
    # Find the rightmost comma
    comma_idx = value.rfind(",")

    if comma_idx == -1:
        # No comma found
        if required:
            raise ValueError(
                f"Invalid format: '{value}'. Expected format: 'first_part,second_part'"
            )
        # Allow just the first part if not required
        first_part = value.strip()
        if not first_part:
            raise ValueError(f"Invalid format: '{value}'. First part cannot be empty.")
        return (first_part, None)

    first_part = value[:comma_idx].strip()
    second_part_str = value[comma_idx + 1 :].strip()

    if not first_part:
        raise ValueError(f"Invalid format: '{value}'. First part cannot be empty.")

    if not second_part_str:
        raise ValueError(f"Invalid format: '{value}'. Second part cannot be empty.")

    try:
        second_part = value_type(second_part_str)
    except ValueError as e:
        raise ValueError(
            f"Invalid format: '{value}'. "
            f"Second part '{second_part_str}' cannot be converted to {value_type.__name__}: {e}"
        ) from e

    return (first_part, second_part)


def parse_tuples_from_list(
    values: List[str], value_type: type = int, required: bool = True
) -> List[Tuple[str, Optional[int]]]:
    """Parse a list of comma-separated tuple strings.

    Args:
        values: List of strings each in format "first_part,second_part" or just "first_part"
        value_type: Type to convert the second part to (default: int)
        required: If True, second part must be present. If False, allows "first_part" only.

    Returns:
        List of parsed tuples with optional second part

    Raises:
        ValueError: If any value has invalid format
    """
    result = []
    for value in values:
        try:
            result.append(
                parse_comma_separated_tuple(value, value_type, required=required)
            )
        except ValueError as e:
            raise ValueError(f"Error parsing '{value}': {e}") from e
    return result
