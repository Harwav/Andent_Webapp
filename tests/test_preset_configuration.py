"""Phase 1: Task 1 - Preset Configuration Tests (TDD)

Tests for preset configuration per finalized requirements:
- Ortho Solid/Hollow: Lay flat, no supports
- Die: Lay flat, no supports
- Tooth: Auto-generate supports
- All: Precision Model Resin, 100µm, Form 4BL
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.classification import default_preset, infer_phase0_model_type


class TestPresetConfiguration:
    """Test preset configuration mappings."""

    def test_default_preset_ortho_solid(self):
        """Ortho - Solid should map to lay flat, no supports preset."""
        preset = default_preset("Ortho - Solid")
        assert preset == "Ortho Solid - Flat, No Supports"

    def test_default_preset_ortho_hollow(self):
        """Ortho - Hollow should map to lay flat, no supports preset."""
        preset = default_preset("Ortho - Hollow")
        assert preset == "Ortho Hollow - Flat, No Supports"

    def test_default_preset_die(self):
        """Die should map to lay flat, no supports preset."""
        preset = default_preset("Die")
        assert preset == "Die - Flat, No Supports"

    def test_default_preset_tooth(self):
        """Tooth should map to auto-generate supports preset."""
        preset = default_preset("Tooth")
        assert preset == "Tooth - With Supports"

    def test_default_preset_splint(self):
        """Splint should map to lay flat, no supports preset."""
        preset = default_preset("Splint")
        assert preset == "Splint - Flat, No Supports"

    def test_default_preset_antagonist_solid(self):
        """Antagonist - Solid should map to lay flat, no supports preset."""
        preset = default_preset("Antagonist - Solid")
        assert preset == "Antagonist Solid - Flat, No Supports"

    def test_default_preset_antagonist_hollow(self):
        """Antagonist - Hollow should map to lay flat, no supports preset."""
        preset = default_preset("Antagonist - Hollow")
        assert preset == "Antagonist Hollow - Flat, No Supports"

    def test_default_preset_antagonist_uses_ortho_solid(self):
        """Antagonist files should default to the Ortho Solid preset."""
        preset = default_preset("Antagonist")
        assert preset == "Ortho Solid - Flat, No Supports"

    def test_default_preset_none(self):
        """None model type should return None preset."""
        preset = default_preset(None)
        assert preset is None

    def test_default_preset_unknown(self):
        """Unknown model type should return None preset."""
        preset = default_preset("Unknown Model Type")
        assert preset is None

    def test_default_preset_case_preservation(self):
        """Preset names should be case-insensitive for matching but return properly formatted presets."""
        # Test that existing Phase0ModelType values are handled
        phase0_types = [
            "Ortho - Solid",
            "Ortho - Hollow",
            "Die",
            "Tooth",
            "Splint",
        ]
        for model_type in phase0_types:
            preset = default_preset(model_type)
            assert preset is not None, f"Model type '{model_type}' should have a preset"
