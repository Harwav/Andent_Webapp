"""
Batch Optimizer - Dimension-Based Smart Batching

This module provides intelligent batching based on STL model dimensions
to optimize build plate utilization.

See: docs/SPEC_Smart_Batching.md for full specification.
"""

import os
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .cache import get_cache

try:
    from stl import mesh
    NUMPY_STL_AVAILABLE = True
except ImportError:
    mesh = None
    NUMPY_STL_AVAILABLE = False
    logging.warning("numpy-stl not available. Smart batching will fall back to fixed size.")


# Build plate dimensions (width_mm, depth_mm) - from constants.py
BUILD_PLATES = {
    "Form 4": (200.0, 125.0),
    "Form 4B": (200.0, 125.0),
    "Form 4L": (335.0, 200.0),
    "Form 4BL": (335.0, 200.0),
    "Form 3": (145.0, 145.0),
    "Form 3B": (145.0, 145.0),
    "Form 3L": (335.0, 200.0),
    "Form 3BL": (335.0, 200.0),
}

# Default build plate (Form 4)
DEFAULT_BUILD_PLATE = (200.0, 125.0)

# Arch-specific tuning for dental aligners on Form 4 / 4B class plates.
ARCH_TARGET_BATCH_SIZE = 8
ARCH_INTERLOCK_WIDTH_FACTOR = 0.84
ARCH_SHELF_DEPTH_FACTOR = 0.90
ARCH_DOMINANT_THRESHOLD = 0.70


@dataclass
class STLDimensions:
    """Bounding box dimensions for an STL file."""
    file_path: str
    x_mm: float  # Width
    y_mm: float  # Depth
    z_mm: float  # Height
    footprint_mm2: float  # X × Y

    @property
    def footprint(self) -> float:
        return self.footprint_mm2


def get_stl_dimensions(file_path: str) -> Optional[STLDimensions]:
    """
    Extract bounding box dimensions from an STL file.

    Args:
        file_path: Path to the STL file

    Returns:
        STLDimensions object or None if extraction fails
    """
    if not NUMPY_STL_AVAILABLE:
        return None

    try:
        cache = get_cache()
        cached_dimensions = cache.get_dimensions(file_path)
        if cached_dimensions is not None:
            logging.debug(f"Cache hit for STL dimensions: {os.path.basename(file_path)}")
            return STLDimensions(file_path=file_path, **cached_dimensions)

        stl_mesh = mesh.Mesh.from_file(file_path)

        # Get bounding box
        min_coords = stl_mesh.min_
        max_coords = stl_mesh.max_

        x_mm = max_coords[0] - min_coords[0]
        y_mm = max_coords[1] - min_coords[1]
        z_mm = max_coords[2] - min_coords[2]

        dimensions = STLDimensions(
            file_path=file_path,
            x_mm=round(x_mm, 2),
            y_mm=round(y_mm, 2),
            z_mm=round(z_mm, 2),
            footprint_mm2=round(x_mm * y_mm, 2)
        )
        cache.set_dimensions(
            file_path,
            {
                "x_mm": dimensions.x_mm,
                "y_mm": dimensions.y_mm,
                "z_mm": dimensions.z_mm,
                "footprint_mm2": dimensions.footprint_mm2,
            },
        )
        return dimensions
    except Exception as e:
        logging.warning(f"Failed to get dimensions for {os.path.basename(file_path)}: {e}")
        return None


def get_stl_volume_ml(file_path: str) -> Optional[float]:
    """
    Estimate raw mesh volume in milliliters from an STL file.

    The STL is assumed to use millimeter units, so mm^3 / 1000 = mL.
    """
    if not NUMPY_STL_AVAILABLE:
        return None

    try:
        cache = get_cache()
        cached_volume = cache.get_volume(file_path)
        if cached_volume is not None:
            logging.debug(f"Cache hit for STL volume: {os.path.basename(file_path)}")
            return cached_volume

        stl_mesh = mesh.Mesh.from_file(file_path)
        volume_mm3, _, _ = stl_mesh.get_mass_properties()
        volume_ml = round(abs(volume_mm3) / 1000.0, 3)
        cache.set_volume(file_path, volume_ml)
        return volume_ml
    except Exception as e:
        logging.warning(f"Failed to get volume for {os.path.basename(file_path)}: {e}")
        return None


def get_build_plate_for_printer(printer_family: str) -> Tuple[float, float]:
    """
    Get build plate dimensions for a printer family.

    Args:
        printer_family: Printer family name (e.g., "Form 4", "Form 4L")

    Returns:
        Tuple of (width_mm, depth_mm)
    """
    return BUILD_PLATES.get(printer_family, DEFAULT_BUILD_PLATE)


class BatchOptimizer:
    """
    Optimizes batch sizes based on model dimensions and build plate capacity.

    Usage:
        optimizer = BatchOptimizer(
            build_plate=(200, 125),  # Form 4
            spacing_mm=0.5,
            efficiency=0.72
        )
        batches = optimizer.calculate_batches(stl_files)
    """

    def __init__(
        self,
        build_plate: Tuple[float, float] = DEFAULT_BUILD_PLATE,
        spacing_mm: float = 0.5,
        efficiency: float = 0.72,
        max_batch_size: int = 20,
        min_batch_size: int = 1,
        depth_tolerance: float = 1.0,
    ):
        """
        Initialize the batch optimizer.

        Args:
            build_plate: (width_mm, depth_mm) tuple
            spacing_mm: Spacing between models (from user settings)
            efficiency: Packing efficiency factor (0.72 = 72%)
            max_batch_size: Maximum files per batch (safety cap)
            min_batch_size: Minimum files per batch
            depth_tolerance: Multiplier applied to plate_depth in the shelf-pack
                heuristic (default 1.0 = strict). Set > 1.0 when the upstream
                layout engine (PreForm) is known to pack more efficiently than
                the 2D shelf estimate — e.g. 1.10 gives 10% extra depth budget.
        """
        self.plate_width = build_plate[0]
        self.plate_depth = build_plate[1]
        self.spacing_mm = spacing_mm
        self.efficiency = efficiency
        self.max_batch_size = max_batch_size
        self.min_batch_size = min_batch_size
        self.depth_tolerance = depth_tolerance

        # Calculate effective build area
        self.effective_area = self.plate_width * self.plate_depth * self.efficiency

        logging.debug(
            f"BatchOptimizer initialized: plate={build_plate}, "
            f"spacing={spacing_mm}mm, efficiency={efficiency}, "
            f"effective_area={self.effective_area:.0f}mm²"
        )

    def _candidate_orientations(self, dims: STLDimensions) -> List[Tuple[float, float]]:
        """Return usable footprint candidates for a model, including rotation."""
        spacing_pad = self.spacing_mm * 0.5
        candidates = [(dims.x_mm + spacing_pad, dims.y_mm + spacing_pad)]
        rotated = (dims.y_mm + spacing_pad, dims.x_mm + spacing_pad)
        if rotated != candidates[0]:
            candidates.append(rotated)
        return candidates

    def _is_form4_class_plate(self) -> bool:
        """True when the active plate matches Form 4 / 4B dimensions."""
        return abs(self.plate_width - 200.0) < 0.1 and abs(self.plate_depth - 125.0) < 0.1

    def _is_arch_like(self, dims: STLDimensions) -> bool:
        """
        Lightweight heuristic for common aligner arches.

        This keeps smart batching fast by avoiding extra mesh analysis while
        still recognizing the horseshoe-style footprints used in this app.
        """
        long_side = max(dims.x_mm, dims.y_mm)
        short_side = min(dims.x_mm, dims.y_mm)
        aspect_ratio = long_side / short_side if short_side > 0 else 0.0

        return (
            45.0 <= long_side <= 95.0 and
            25.0 <= short_side <= 70.0 and
            1.10 <= aspect_ratio <= 2.60 and
            dims.z_mm <= 25.0
        )

    def _is_arch_dominant(self, batch_dims: List[STLDimensions]) -> bool:
        """True when most models in the set look like aligner arches."""
        if not batch_dims or not self._is_form4_class_plate():
            return False

        arch_count = sum(1 for dims in batch_dims if self._is_arch_like(dims))
        return (arch_count / len(batch_dims)) >= ARCH_DOMINANT_THRESHOLD

    def _can_pack_batch(self, batch_dims: List[STLDimensions]) -> bool:
        """
        Estimate whether the current batch can fit on the plate.

        This uses a shelf pack instead of a pure area cap so smart batching
        tracks the real plate dimensions more closely.
        """
        shelves: List[Dict[str, float]] = []
        total_depth = 0.0
        arch_mode = self._is_arch_dominant(batch_dims)

        for dims in batch_dims:
            best_existing = None
            is_arch = arch_mode and self._is_arch_like(dims)

            for width, depth in self._candidate_orientations(dims):
                for idx, shelf in enumerate(shelves):
                    # Allow up to 20% overflow — PreForm's auto-layout handles minor depth variance
                    if depth > shelf["depth"] * 1.20:
                        continue

                    width_to_add = width
                    if is_arch and shelf.get("arch_items", 0) > 0:
                        width_to_add *= ARCH_INTERLOCK_WIDTH_FACTOR

                    new_width = shelf["width"] + width_to_add
                    if new_width > self.plate_width:
                        continue

                    score = (width_to_add, self.plate_width - new_width, idx)
                    candidate = (idx, width_to_add, depth, score)
                    if best_existing is None or candidate[-1] < best_existing[-1]:
                        best_existing = candidate

            if best_existing is not None:
                shelf_idx, width_to_add, depth, _ = best_existing
                shelf = shelves[shelf_idx]
                shelf["width"] += width_to_add
                shelf["depth"] = max(shelf["depth"], depth)
                if is_arch:
                    shelf["arch_items"] = shelf.get("arch_items", 0) + 1
                continue

            best_new = None
            for width, depth in self._candidate_orientations(dims):
                depth_to_add = depth
                if is_arch and shelves:
                    depth_to_add *= ARCH_SHELF_DEPTH_FACTOR

                if total_depth + depth_to_add > self.plate_depth * self.depth_tolerance:
                    continue

                row_capacity = max(1, int(self.plate_width // width))
                if is_arch:
                    additional_capacity = int(
                        max(self.plate_width - width, 0.0) //
                        max(width * ARCH_INTERLOCK_WIDTH_FACTOR, 1.0)
                    )
                    row_capacity = max(row_capacity, 1 + additional_capacity)
                score = (-row_capacity, depth_to_add, width)
                candidate = (width, depth, depth_to_add, score)
                if best_new is None or candidate[-1] < best_new[-1]:
                    best_new = candidate

            if best_new is None:
                return False

            width, depth, depth_to_add, _ = best_new
            shelves.append({
                "width": width,
                "depth": depth,
                "arch_items": 1 if is_arch else 0
            })
            total_depth += depth_to_add

        return True

    def _build_greedy_batches(
        self,
        valid_files: List[Tuple[str, STLDimensions]]
    ) -> List[List[str]]:
        """Original greedy batch construction with fit checks."""
        batches: List[List[str]] = []
        current_batch: List[str] = []
        current_batch_dims: List[STLDimensions] = []

        for path, dims in valid_files:
            proposed_dims = current_batch_dims + [dims]
            can_fit_count = len(current_batch) < self.max_batch_size
            can_fit_layout = can_fit_count and self._can_pack_batch(proposed_dims)

            if can_fit_layout:
                current_batch.append(path)
                current_batch_dims.append(dims)
            else:
                if current_batch:
                    batches.append(current_batch)
                current_batch = [path]
                current_batch_dims = [dims]

                if not self._can_pack_batch(current_batch_dims):
                    logging.warning(
                        "Model %s exceeds the estimated build plate footprint and will be placed alone.",
                        os.path.basename(path)
                    )

        if current_batch:
            batches.append(current_batch)

        return batches

    def _build_arch_target_batches(
        self,
        valid_files: List[Tuple[str, STLDimensions]]
    ) -> List[List[str]]:
        """
        Build batches for arch-heavy Form 4 / 4B workloads.

        Strategy:
        - Try to hit at least 8 first.
        - If 8 fits, probe upward and keep the largest verified fit.
        - If 8 does not fit, step down until something fits.
        """
        remaining = list(valid_files)
        batches: List[List[str]] = []

        while remaining:
            max_candidate = min(len(remaining), self.max_batch_size)
            target_size = min(max_candidate, ARCH_TARGET_BATCH_SIZE)
            best_size = 0

            candidate_dims = [dims for _, dims in remaining[:target_size]]
            if self._can_pack_batch(candidate_dims):
                best_size = target_size
                probe_size = target_size + 1
                while probe_size <= max_candidate:
                    probe_dims = [dims for _, dims in remaining[:probe_size]]
                    if not self._can_pack_batch(probe_dims):
                        break
                    best_size = probe_size
                    probe_size += 1
            else:
                for fallback_size in range(target_size - 1, self.min_batch_size - 1, -1):
                    fallback_dims = [dims for _, dims in remaining[:fallback_size]]
                    if self._can_pack_batch(fallback_dims):
                        best_size = fallback_size
                        break

            if best_size <= 0:
                best_size = 1

            batch = [path for path, _ in remaining[:best_size]]
            batches.append(batch)
            del remaining[:best_size]

        return batches

    def calculate_batches(
        self,
        stl_files: List[str],
        fallback_batch_size: int = 10
    ) -> List[List[str]]:
        """
        Calculate optimized batches based on model dimensions.

        Args:
            stl_files: List of STL file paths
            fallback_batch_size: Batch size to use if dimension extraction fails

        Returns:
            List of batches, where each batch is a list of file paths
        """
        if not stl_files:
            return []

        # Extract dimensions for all files
        file_dims: List[Tuple[str, Optional[STLDimensions]]] = []
        for path in stl_files:
            dims = get_stl_dimensions(path)
            file_dims.append((path, dims))

        # Check how many dimensions were successfully extracted
        valid_count = sum(1 for _, d in file_dims if d is not None)
        total_count = len(file_dims)

        # Fall back to fixed batching if less than 50% succeeded
        if valid_count < total_count * 0.5:
            logging.warning(
                f"Only {valid_count}/{total_count} STL dimensions extracted. "
                f"Falling back to fixed batch size of {fallback_batch_size}."
            )
            return self._fixed_batches(stl_files, fallback_batch_size)

        # Separate valid and invalid files
        valid_files = [(p, d) for p, d in file_dims if d is not None]
        invalid_files = [p for p, d in file_dims if d is None]

        # Sort by footprint (largest first for better packing)
        valid_files.sort(key=lambda x: x[1].footprint, reverse=True)

        valid_dims_only = [dims for _, dims in valid_files]
        if self._is_arch_dominant(valid_dims_only):
            batches = self._build_arch_target_batches(valid_files)
        else:
            batches = self._build_greedy_batches(valid_files)

        # Add invalid files to the end (in a separate batch if needed)
        if invalid_files:
            logging.info(f"Adding {len(invalid_files)} files with unknown dimensions to batches")
            # Try to fit into last batch or create new one
            for path in invalid_files:
                if batches and len(batches[-1]) < self.max_batch_size:
                    batches[-1].append(path)
                else:
                    batches.append([path])

        # Log batch composition
        batch_sizes = [len(b) for b in batches]
        logging.info(
            f"Smart batching: {len(stl_files)} files → {len(batches)} batches "
            f"(sizes: {batch_sizes})"
        )

        return batches

    def _fixed_batches(self, stl_files: List[str], batch_size: int) -> List[List[str]]:
        """Create fixed-size batches (fallback method)."""
        batches = []
        for i in range(0, len(stl_files), batch_size):
            batch = stl_files[i:i + batch_size]
            batches.append(batch)

        logging.info(
            f"Fixed batching: {len(stl_files)} files → {len(batches)} batches "
            f"(batch_size={batch_size})"
        )
        return batches

    def estimate_batch_count(self, stl_files: List[str]) -> int:
        """
        Estimate how many batches will be needed without full calculation.

        Useful for progress estimation.
        """
        batches = self.calculate_batches(stl_files)
        return len(batches)

    def get_stats(self, stl_files: List[str]) -> Dict:
        """
        Get statistics about the batching for the given files.

        Returns dict with:
        - total_files: Number of files
        - batch_count: Number of batches
        - batch_sizes: List of batch sizes
        - avg_files_per_batch: Average files per batch
        - build_plate_utilization: Estimated utilization
        """
        batches = self.calculate_batches(stl_files)

        if not batches:
            return {
                "total_files": 0,
                "batch_count": 0,
                "batch_sizes": [],
                "avg_files_per_batch": 0,
                "estimated_utilization": 0
            }

        batch_sizes = [len(b) for b in batches]

        return {
            "total_files": len(stl_files),
            "batch_count": len(batches),
            "batch_sizes": batch_sizes,
            "avg_files_per_batch": sum(batch_sizes) / len(batch_sizes),
            "build_plate": (self.plate_width, self.plate_depth),
            "effective_area_mm2": self.effective_area,
            "spacing_mm": self.spacing_mm,
            "efficiency": self.efficiency
        }


# Convenience function for quick batching
def create_smart_batches(
    stl_files: List[str],
    printer_family: str = "Form 4",
    spacing_mm: float = 0.5,
    max_batch_size: int = 10
) -> List[List[str]]:
    """
    Convenience function to create smart batches.

    Args:
        stl_files: List of STL file paths
        printer_family: Printer family name
        spacing_mm: Model spacing from settings
        max_batch_size: Maximum files per batch (used as fallback)

    Returns:
        List of batches
    """
    build_plate = get_build_plate_for_printer(printer_family)
    optimizer = BatchOptimizer(
        build_plate=build_plate,
        spacing_mm=spacing_mm,
        max_batch_size=max_batch_size
    )
    return optimizer.calculate_batches(stl_files, fallback_batch_size=max_batch_size)


if __name__ == "__main__":
    # Simple test
    import sys

    if len(sys.argv) > 1:
        folder = sys.argv[1]
    else:
        folder = "/Users/marcusliang/Library/CloudStorage/GoogleDrive-marcus.liang@formlabs.com/Shared drives/APAC SE Resources/06. Projects/202507 Aligner Batch Hollowing/Sample Data copy"

    # Find STL files
    stl_files = []
    for root, dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith('.stl'):
                stl_files.append(os.path.join(root, f))

    print(f"Found {len(stl_files)} STL files")

    if stl_files:
        optimizer = BatchOptimizer(spacing_mm=0.5)
        stats = optimizer.get_stats(stl_files)
        print(f"\nBatching Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
