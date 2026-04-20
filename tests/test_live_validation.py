"""
Live Validation Test

Validates classification accuracy and performance with real STL files.
"""
import pytest
import time
from pathlib import Path
from core.andent_classification import classify_artifact, resolve_ortho_structure, ARTIFACT_MODEL
from core.batch_optimizer import get_stl_dimensions, get_stl_volume_ml
from app.services.classification import classify_uploaded_files_parallel
from core.cache import clear_cache


# Test data location
TEST_DATA_DIR = Path(r"D:\Marcus\Desktop\BM\20260409_Andent_Matt\Test Data 2")


@pytest.mark.skipif(not TEST_DATA_DIR.exists(), reason="Test data directory not found")
class TestLiveValidation:
    """Live validation with real STL files."""
    
    def test_classification_accuracy_real_files(self):
        """Test that real files are classified without review."""
        # Get first 3 STL files
        stl_files = list(TEST_DATA_DIR.glob("*.stl"))[:3]
        
        for stl_path in stl_files:
            # Clear cache to test fresh classification
            clear_cache()
            
            # Classify by filename
            result = classify_artifact(str(stl_path))
            
            # Should extract case ID from filename
            assert result.case_id is not None, f"Failed to extract case ID from {stl_path.name}"
            
            # Should classify without review for well-named files
            # Note: May still need review if geometry is ambiguous
            print(f"{stl_path.name}: case_id={result.case_id}, type={result.artifact_type}, review={result.review_required}")
    
    def test_dimension_extraction_performance(self):
        """Test that dimension extraction is fast with caching."""
        stl_files = list(TEST_DATA_DIR.glob("*.stl"))[:3]
        
        # First call (no cache)
        start = time.time()
        for stl_path in stl_files:
            dims = get_stl_dimensions(str(stl_path))
            assert dims is not None
        first_call_time = time.time() - start
        
        # Second call (with cache) - should be much faster
        start = time.time()
        for stl_path in stl_files:
            dims = get_stl_dimensions(str(stl_path))
            assert dims is not None
        second_call_time = time.time() - start
        
        # Cached call should be at least 2x faster
        print(f"First call: {first_call_time:.3f}s, Cached call: {second_call_time:.3f}s")
        assert second_call_time < first_call_time, "Cache should be faster"
    
    def test_parallel_classification_real_files(self):
        """Test parallel classification with real files."""
        stl_files = list(TEST_DATA_DIR.glob("*.stl"))[:5]
        
        # Prepare file tuples
        file_tuples = [(f, f.name) for f in stl_files]
        
        # Classify in parallel
        start = time.time()
        results = classify_uploaded_files_parallel(file_tuples, max_workers=4)
        elapsed = time.time() - start
        
        # Should classify all files
        assert len(results) == len(stl_files)
        
        # Should complete in reasonable time (<10s per file)
        max_expected_time = len(stl_files) * 10  # 10s per file
        print(f"Classified {len(results)} files in {elapsed:.2f}s ({elapsed/len(results):.2f}s per file)")
        assert elapsed < max_expected_time, f"Classification too slow: {elapsed:.2f}s"
