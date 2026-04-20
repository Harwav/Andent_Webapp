"""
Parallel Classification Tests

Tests for parallel batch classification performance.
"""
import pytest
from pathlib import Path
from app.services.classification import classify_uploaded_files_parallel


class TestParallelClassification:
    """Test parallel classification functionality."""
    
    def test_parallel_classification_returns_results(self, tmp_path):
        """Test that parallel classification returns results for all files."""
        # Create simple test STL files
        test_files = []
        for i in range(5):
            stl_path = tmp_path / f"test_{i}.stl"
            # Minimal valid STL (solid with one triangle)
            stl_content = f"""solid test_{i}
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 10 0 0
      vertex 5 10 0
    endloop
  endfacet
endsolid test_{i}
"""
            stl_path.write_text(stl_content)
            test_files.append((stl_path, f"test_{i}.stl"))
        
        results = classify_uploaded_files_parallel(test_files, max_workers=2)
        
        assert len(results) == 5
        # All should have file names
        assert all(r.file_name.startswith("test_") for r in results)
    
    def test_parallel_classification_handles_errors_gracefully(self, tmp_path):
        """Test that parallel classification handles errors without crashing."""
        # Create one valid and one invalid file
        valid_stl = tmp_path / "valid.stl"
        valid_stl.write_text("""solid test
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 10 0 0
      vertex 5 10 0
    endloop
  endfacet
endsolid test
""")
        
        invalid_stl = tmp_path / "invalid.stl"
        invalid_stl.write_text("This is not an STL file")
        
        test_files = [
            (valid_stl, "valid.stl"),
            (invalid_stl, "invalid.stl"),
        ]
        
        # Should not crash, should return results for both
        results = classify_uploaded_files_parallel(test_files, max_workers=2)
        
        assert len(results) == 2
        # Invalid file should have review_required=True
        invalid_result = next(r for r in results if r.file_name == "invalid.stl")
        assert invalid_result.review_required is True
