# stl_validator.py
"""
STL File Validation Module for FormFlow Dent v0.4.2

Pre-validates STL files before sending to PreFormServer API to catch common
issues early and provide clear, user-friendly error messages.

Validation Checks:
1. File existence and accessibility
2. File size (not empty, not too large)
3. STL format validation (binary header or ASCII "solid" keyword)
4. Mesh parsing validation (using numpy-stl if available)
5. Duplicate file detection within batch
"""

import os
import logging
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from .constants import STL_MIN_FILE_SIZE, STL_MAX_FILE_SIZE, STL_WARN_LARGE_SIZE


class ValidationStatus(Enum):
    """Validation result status codes."""
    OK = "ok"
    MISSING = "missing"
    EMPTY = "empty"
    TOO_LARGE = "too_large"
    INVALID_FORMAT = "invalid_format"
    CORRUPTED = "corrupted"
    DUPLICATE = "duplicate"
    PERMISSION_ERROR = "permission_error"
    WARNING = "warning"  # File is valid but has warnings


@dataclass
class ValidationResult:
    """Result of validating a single STL file."""
    is_valid: bool
    status: ValidationStatus
    message: str
    file_path: str
    file_size: int = 0
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class BatchValidationResult:
    """Result of validating a batch of STL files."""
    valid_files: List[str]
    invalid_files: Dict[str, ValidationResult]
    warnings: Dict[str, List[str]]
    total_files: int
    valid_count: int
    invalid_count: int
    warning_count: int

    def get_summary(self) -> str:
        """Get a human-readable summary of the validation results."""
        if self.invalid_count == 0 and self.warning_count == 0:
            return f"All {self.total_files} files validated successfully."

        parts = [f"Found {self.total_files} files:"]
        parts.append(f"{self.valid_count} valid")

        if self.invalid_count > 0:
            parts.append(f"{self.invalid_count} invalid")

        if self.warning_count > 0:
            parts.append(f"{self.warning_count} with warnings")

        return ", ".join(parts)


class STLValidator:
    """Pre-validation of STL files before API submission."""

    # Binary STL header size
    BINARY_HEADER_SIZE = 80
    # Binary STL triangle count size
    TRIANGLE_COUNT_SIZE = 4
    # ASCII STL starts with "solid"
    ASCII_MAGIC = b"solid"

    def __init__(self):
        """Initialize the STL validator."""
        self._numpy_stl_available = self._check_numpy_stl()

    def _check_numpy_stl(self) -> bool:
        """Check if numpy-stl is available for mesh validation."""
        try:
            from stl import mesh
            return True
        except ImportError:
            logging.debug("numpy-stl not available - mesh validation will be skipped")
            return False

    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate a single STL file.

        Args:
            file_path: Path to the STL file

        Returns:
            ValidationResult with validation status and details
        """
        warnings = []

        # Check 1: File exists
        if not os.path.exists(file_path):
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.MISSING,
                message=f"File not found: {os.path.basename(file_path)}",
                file_path=file_path
            )

        # Check 2: File is accessible
        if not os.access(file_path, os.R_OK):
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.PERMISSION_ERROR,
                message=f"Cannot read file (permission denied): {os.path.basename(file_path)}",
                file_path=file_path
            )

        # Check 3: File size
        try:
            file_size = os.path.getsize(file_path)
        except OSError as e:
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.PERMISSION_ERROR,
                message=f"Cannot access file: {os.path.basename(file_path)} - {e}",
                file_path=file_path
            )

        if file_size == 0:
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.EMPTY,
                message=f"File is empty (0 bytes): {os.path.basename(file_path)}",
                file_path=file_path,
                file_size=0
            )

        if file_size < STL_MIN_FILE_SIZE:
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.INVALID_FORMAT,
                message=f"File too small to be valid STL ({file_size} bytes): {os.path.basename(file_path)}",
                file_path=file_path,
                file_size=file_size
            )

        if file_size > STL_MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            max_mb = STL_MAX_FILE_SIZE / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.TOO_LARGE,
                message=f"File too large ({size_mb:.1f}MB, max {max_mb:.0f}MB): {os.path.basename(file_path)}",
                file_path=file_path,
                file_size=file_size
            )

        # Warning for large files
        if file_size > STL_WARN_LARGE_SIZE:
            size_mb = file_size / (1024 * 1024)
            warnings.append(f"Large file ({size_mb:.1f}MB) - processing may be slow")

        # Check 4: STL format validation
        format_valid, format_error = self._validate_stl_format(file_path)
        if not format_valid:
            return ValidationResult(
                is_valid=False,
                status=ValidationStatus.INVALID_FORMAT,
                message=f"Not a valid STL file: {os.path.basename(file_path)} - {format_error}",
                file_path=file_path,
                file_size=file_size
            )

        # Check 5: Try to parse mesh (if numpy-stl available)
        if self._numpy_stl_available:
            mesh_valid, mesh_error = self._try_parse_mesh(file_path)
            if not mesh_valid:
                return ValidationResult(
                    is_valid=False,
                    status=ValidationStatus.CORRUPTED,
                    message=f"Corrupted STL file: {os.path.basename(file_path)} - {mesh_error}",
                    file_path=file_path,
                    file_size=file_size
                )

        # File is valid
        return ValidationResult(
            is_valid=True,
            status=ValidationStatus.WARNING if warnings else ValidationStatus.OK,
            message="OK" if not warnings else "; ".join(warnings),
            file_path=file_path,
            file_size=file_size,
            warnings=warnings
        )

    def _validate_stl_format(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Validate STL file format (binary or ASCII).

        Args:
            file_path: Path to the STL file

        Returns:
            (is_valid, error_message)
        """
        try:
            with open(file_path, 'rb') as f:
                # Read first 80 bytes (binary header)
                header = f.read(self.BINARY_HEADER_SIZE)

                if len(header) < self.BINARY_HEADER_SIZE:
                    return False, "File too short for STL format"

                # Check for ASCII STL (starts with "solid")
                if header[:5] == self.ASCII_MAGIC:
                    # Could be ASCII STL - verify it's not binary with "solid" in header
                    # ASCII STL should have "facet" somewhere after "solid"
                    f.seek(0)
                    first_1k = f.read(1024)
                    if b'facet' in first_1k or b'endsolid' in first_1k:
                        return True, None  # Valid ASCII STL
                    # Binary STL that happens to start with "solid"
                    # Fall through to binary validation

                # Validate as binary STL
                # After 80-byte header, next 4 bytes are triangle count
                count_bytes = f.read(self.TRIANGLE_COUNT_SIZE)
                if len(count_bytes) < self.TRIANGLE_COUNT_SIZE:
                    return False, "Missing triangle count in binary STL"

                # Triangle count as little-endian uint32
                triangle_count = int.from_bytes(count_bytes, byteorder='little')

                # Each triangle is 50 bytes (12 floats * 4 bytes + 2 attribute bytes)
                expected_size = self.BINARY_HEADER_SIZE + self.TRIANGLE_COUNT_SIZE + (triangle_count * 50)
                actual_size = os.path.getsize(file_path)

                # Allow some tolerance for padding
                if abs(actual_size - expected_size) > 100:
                    # Could still be ASCII - check more thoroughly
                    f.seek(0)
                    content = f.read(5000)
                    if b'solid' in content and b'facet' in content:
                        return True, None  # Valid ASCII STL

                    return False, f"Invalid binary STL: expected ~{expected_size} bytes, got {actual_size}"

                return True, None

        except IOError as e:
            return False, f"Cannot read file: {e}"
        except Exception as e:
            return False, f"Format validation error: {e}"

    def _try_parse_mesh(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Try to parse the STL file using numpy-stl.

        Args:
            file_path: Path to the STL file

        Returns:
            (is_valid, error_message)
        """
        try:
            from stl import mesh
            stl_mesh = mesh.Mesh.from_file(file_path)

            # Basic sanity checks
            if len(stl_mesh.vectors) == 0:
                return False, "STL contains no triangles"

            return True, None

        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            return False, error_msg

    def validate_batch(self, file_paths: List[str],
                       seen_filenames: Optional[Dict[str, str]] = None) -> BatchValidationResult:
        """Validate multiple STL files, including duplicate detection.

        OPT-1: Added seen_filenames parameter for cross-batch duplicate detection.
        When processing per-batch, pass the same dict across batches to detect
        duplicates even when they are in different batches.

        Args:
            file_paths: List of paths to STL files
            seen_filenames: Optional dict mapping lowercase filename to full path.
                           If None, a fresh dict is created for this batch only.
                           If provided, duplicates are detected across batches.

        Returns:
            BatchValidationResult with validation results for all files
        """
        valid_files = []
        invalid_files = {}
        warnings = {}
        # Use provided dict or create new one for single-batch validation
        if seen_filenames is None:
            seen_filenames = {}

        for file_path in file_paths:
            # Check for duplicate filenames in batch
            filename = os.path.basename(file_path).lower()
            if filename in seen_filenames:
                invalid_files[file_path] = ValidationResult(
                    is_valid=False,
                    status=ValidationStatus.DUPLICATE,
                    message=f"Duplicate filename in batch: {os.path.basename(file_path)} (also in {os.path.dirname(seen_filenames[filename])})",
                    file_path=file_path
                )
                continue

            seen_filenames[filename] = file_path

            # Validate the file
            result = self.validate_file(file_path)

            if result.is_valid:
                valid_files.append(file_path)
                if result.warnings:
                    warnings[file_path] = result.warnings
            else:
                invalid_files[file_path] = result

        return BatchValidationResult(
            valid_files=valid_files,
            invalid_files=invalid_files,
            warnings=warnings,
            total_files=len(file_paths),
            valid_count=len(valid_files),
            invalid_count=len(invalid_files),
            warning_count=len(warnings)
        )

    def get_error_message(self, status: ValidationStatus) -> str:
        """Get a user-friendly error message for a validation status.

        Args:
            status: The validation status

        Returns:
            User-friendly error description
        """
        messages = {
            ValidationStatus.OK: "File is valid",
            ValidationStatus.MISSING: "File not found",
            ValidationStatus.EMPTY: "File is empty (0 bytes)",
            ValidationStatus.TOO_LARGE: "File exceeds maximum size limit",
            ValidationStatus.INVALID_FORMAT: "Not a valid STL file",
            ValidationStatus.CORRUPTED: "STL file appears corrupted",
            ValidationStatus.DUPLICATE: "Duplicate filename in batch",
            ValidationStatus.PERMISSION_ERROR: "Cannot access file (permission denied)",
            ValidationStatus.WARNING: "File valid with warnings",
        }
        return messages.get(status, "Unknown validation error")


# Module-level validator instance for convenience
_validator = None


def get_validator() -> STLValidator:
    """Get the shared STLValidator instance."""
    global _validator
    if _validator is None:
        _validator = STLValidator()
    return _validator


def validate_stl_file(file_path: str) -> ValidationResult:
    """Convenience function to validate a single STL file.

    Args:
        file_path: Path to the STL file

    Returns:
        ValidationResult with validation status and details
    """
    return get_validator().validate_file(file_path)


def validate_stl_batch(file_paths: List[str],
                       seen_filenames: Optional[Dict[str, str]] = None) -> BatchValidationResult:
    """Convenience function to validate a batch of STL files.

    OPT-1: Added seen_filenames parameter for cross-batch duplicate detection.

    Args:
        file_paths: List of paths to STL files
        seen_filenames: Optional dict for tracking filenames across batches.
                       Pass the same dict to each batch call to detect
                       duplicates across batches.

    Returns:
        BatchValidationResult with validation results for all files
    """
    return get_validator().validate_batch(file_paths, seen_filenames)
