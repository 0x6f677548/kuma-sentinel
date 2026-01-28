"""Tests for CLI utility functions."""

import pytest

from kuma_scout.cli.utils import parse_comma_separated_tuple, parse_tuples_from_list


class TestParseCommaSeparatedTuple:
    """Test comma-separated tuple parsing."""

    def test_basic_format(self) -> None:
        """Test basic path,hours format."""
        result = parse_comma_separated_tuple("/data,24")
        assert result == ("/data", 24)

    def test_ssh_path_with_colon(self) -> None:
        """Test SSH path with colon in path."""
        result = parse_comma_separated_tuple("root@fileserver:/mnt/shares,48")
        assert result == ("root@fileserver:/mnt/shares", 48)

    def test_path_with_spaces(self) -> None:
        """Test path with spaces."""
        result = parse_comma_separated_tuple("/path with spaces,30")
        assert result == ("/path with spaces", 30)

    def test_multiple_colons_in_path(self) -> None:
        """Test path with multiple colons (SSH with port)."""
        result = parse_comma_separated_tuple("user@host:22:/path,24")
        assert result == ("user@host:22:/path", 24)

    def test_whitespace_trimming(self) -> None:
        """Test that leading/trailing whitespace is trimmed."""
        result = parse_comma_separated_tuple("  /data  ,  24  ")
        assert result == ("/data", 24)

    def test_missing_comma(self) -> None:
        """Test error when comma is missing."""
        with pytest.raises(ValueError, match="Expected format"):
            parse_comma_separated_tuple("/data24")

    def test_missing_first_part(self) -> None:
        """Test error when first part is empty."""
        with pytest.raises(ValueError, match="First part cannot be empty"):
            parse_comma_separated_tuple(",24")

    def test_missing_second_part(self) -> None:
        """Test error when second part is empty."""
        with pytest.raises(ValueError, match="Second part cannot be empty"):
            parse_comma_separated_tuple("/data,")

    def test_invalid_second_part(self) -> None:
        """Test error when second part is not an integer."""
        with pytest.raises(ValueError, match="cannot be converted to int"):
            parse_comma_separated_tuple("/data,notanumber")

    def test_optional_format_first_part_only(self) -> None:
        """Test optional format with just first part (no second part)."""
        result = parse_comma_separated_tuple("value", required=False)
        assert result == ("value", None)

    def test_optional_format_still_accepts_full_format(self) -> None:
        """Test that optional format still accepts full format."""
        result = parse_comma_separated_tuple("value,42", required=False)
        assert result == ("value", 42)

    def test_required_format_rejects_first_part_only(self) -> None:
        """Test that required=True rejects first part without second part."""
        with pytest.raises(ValueError, match="Expected format"):
            parse_comma_separated_tuple("value", required=True)


class TestParseTuplesFromList:
    """Test parsing multiple comma-separated tuples."""

    def test_single_tuple(self) -> None:
        """Test parsing single tuple."""
        result = parse_tuples_from_list(["/data,24"])
        assert result == [("/data", 24)]

    def test_multiple_tuples(self) -> None:
        """Test parsing multiple tuples."""
        result = parse_tuples_from_list(["/data,24", "/backups,48", "/archive,72"])
        assert result == [
            ("/data", 24),
            ("/backups", 48),
            ("/archive", 72),
        ]

    def test_mixed_paths(self) -> None:
        """Test parsing mixed local and SSH paths."""
        result = parse_tuples_from_list(
            ["/local/path,24", "root@fileserver:/remote/path,48"]
        )
        assert result == [
            ("/local/path", 24),
            ("root@fileserver:/remote/path", 48),
        ]

    def test_empty_list(self) -> None:
        """Test parsing empty list."""
        result = parse_tuples_from_list([])
        assert result == []

    def test_invalid_tuple_in_list(self) -> None:
        """Test error handling for invalid tuple in list."""
        with pytest.raises(ValueError, match="Error parsing"):
            parse_tuples_from_list(["/data,24", "invalid"])

    def test_optional_format_first_part_only_list(self) -> None:
        """Test optional format with first parts only (no second parts)."""
        result = parse_tuples_from_list(["value1", "value2"], required=False)
        assert result == [("value1", None), ("value2", None)]

    def test_optional_format_mixed_with_and_without_second_part(self) -> None:
        """Test optional format mixing values with and without second part."""
        result = parse_tuples_from_list(
            ["value1", "value2,48", "value3"], required=False
        )
        assert result == [
            ("value1", None),
            ("value2", 48),
            ("value3", None),
        ]

    def test_optional_format_complex_first_parts(self) -> None:
        """Test optional format with complex first parts (colons, etc)."""
        result = parse_tuples_from_list(
            [
                "host:path",
                "user@host:path,48",
                "complex.domain.com:/remote",
            ],
            required=False,
        )
        assert result == [
            ("host:path", None),
            ("user@host:path", 48),
            ("complex.domain.com:/remote", None),
        ]
