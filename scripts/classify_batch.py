"""
Batch Classification Script

Classifies all STL files in a directory and produces a comprehensive CSV report.

Usage:
    python scripts/classify_batch.py <input_directory> [output_csv]

Example:
    python scripts/classify_batch.py "D:/Marcus/Desktop/BM/20260409_Andent_Matt/Test Data 2" report.csv
"""
import sys
import csv
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.andent_classification import classify_artifact, resolve_ortho_structure, ARTIFACT_MODEL
from core.batch_optimizer import get_stl_dimensions, get_stl_volume_ml
from app.services.classification import classify_saved_upload
from core.cache import clear_cache, get_cache


def classify_stl_file(stl_path: Path) -> Dict[str, Any]:
    """
    Classify a single STL file and return comprehensive results.
    
    Returns dict with:
    - Filename, file size
    - Case ID, artifact type, workflow
    - Model type, preset, confidence, status
    - Dimensions (X, Y, Z)
    - Volume (mL)
    - Structure (solid/hollow)
    - Review required flag and reason
    - Timing information
    """
    result = {
        'file_name': stl_path.name,
        'file_path': str(stl_path),
        'file_size_mb': round(stl_path.stat().st_size / (1024 * 1024), 2),
    }
    
    start_time = time.time()
    
    try:
        # Get dimensions (cached)
        dims_start = time.time()
        dimensions = get_stl_dimensions(str(stl_path))
        dims_time = time.time() - dims_start
        
        result.update({
            'dimension_x_mm': dimensions.x_mm if dimensions else None,
            'dimension_y_mm': dimensions.y_mm if dimensions else None,
            'dimension_z_mm': dimensions.z_mm if dimensions else None,
            'dimensions_time_ms': round(dims_time * 1000, 2),
        })
        
        # Get volume (cached)
        vol_start = time.time()
        volume_ml = get_stl_volume_ml(str(stl_path))
        vol_time = time.time() - vol_start
        
        result['volume_ml'] = round(volume_ml, 3) if volume_ml else None
        result['volume_time_ms'] = round(vol_time * 1000, 2)
        
        # Classify artifact
        class_start = time.time()
        artifact = classify_artifact(str(stl_path), dims=dimensions)
        class_time = time.time() - class_start
        
        result.update({
            'case_id': artifact.case_id,
            'artifact_type': artifact.artifact_type,
            'workflow': artifact.workflow,
            'artifact_confidence': artifact.confidence,
            'artifact_reasons': '; '.join(artifact.reasons) if artifact.reasons else None,
            'classification_time_ms': round(class_time * 1000, 2),
        })
        
        # Resolve structure (for ortho models)
        struct_start = time.time()
        if artifact.artifact_type in {ARTIFACT_MODEL, 'antagonist', 'model_base'}:
            from core.andent_classification import measure_mesh_thickness_stats
            thickness_stats = measure_mesh_thickness_stats(str(stl_path))
            structure = resolve_ortho_structure(
                artifact,
                dims=dimensions,
                volume_ml=volume_ml,
                thickness_stats=thickness_stats,
            )
            
            result.update({
                'structure': structure.structure if structure else None,
                'structure_confidence': structure.confidence if structure else None,
                'structure_reason': structure.reason if structure else None,
                'fill_ratio': structure.fill_ratio if structure else None,
                'thickness_p10_mm': thickness_stats.thickness_p10,
                'thickness_p50_mm': thickness_stats.thickness_p50,
                'thin_fraction_under_5mm': thickness_stats.thin_fraction_under_5mm,
                'structure_time_ms': round((time.time() - struct_start) * 1000, 2),
            })
        else:
            result.update({
                'structure': None,
                'structure_confidence': None,
                'structure_reason': None,
                'fill_ratio': None,
                'thickness_p10_mm': None,
                'thickness_p50_mm': None,
                'thin_fraction_under_5mm': None,
                'structure_time_ms': 0,
            })
        
        # Derive model type
        from app.services.classification import infer_phase0_model_type, default_preset, derive_confidence, derive_status
        
        model_type = infer_phase0_model_type(stl_path.name, artifact, structure if artifact.artifact_type in {ARTIFACT_MODEL, 'antagonist', 'model_base'} else None)
        preset = default_preset(model_type)
        
        review_required = bool(artifact.review_required or artifact.review_reason)
        confidence = derive_confidence(
            model_type,
            artifact.confidence,
            artifact.case_id,
            upstream_review_required=review_required,
        )
        status = derive_status(confidence, model_type, preset)
        
        result.update({
            'model_type': model_type,
            'preset': preset,
            'confidence': confidence,
            'status': status,
            'review_required': review_required,
            'review_reason': artifact.review_reason,
        })
        
        result['total_time_ms'] = round((time.time() - start_time) * 1000, 2)
        result['error'] = None
        
    except Exception as e:
        result.update({
            'case_id': None,
            'artifact_type': None,
            'workflow': None,
            'model_type': None,
            'preset': None,
            'confidence': 'low',
            'status': 'Needs Review',
            'review_required': True,
            'review_reason': f'Classification error: {str(e)}',
            'error': str(e),
            'total_time_ms': round((time.time() - start_time) * 1000, 2),
        })
    
    return result


def generate_report(stl_files: List[Path], output_csv: Path) -> Dict[str, Any]:
    """
    Generate comprehensive classification report.
    
    Returns summary statistics.
    """
    print(f"\n{'='*80}")
    print(f"BATCH CLASSIFICATION REPORT")
    print(f"{'='*80}")
    print(f"Generated: {datetime.now().isoformat()}")
    print(f"Input Directory: {stl_files[0].parent if stl_files else 'N/A'}")
    print(f"Total Files: {len(stl_files)}")
    print(f"{'='*80}\n")
    
    # Clear cache before starting
    clear_cache()
    
    results = []
    total_start = time.time()
    
    for i, stl_path in enumerate(stl_files, 1):
        print(f"[{i}/{len(stl_files)}] Classifying: {stl_path.name}")
        result = classify_stl_file(stl_path)
        results.append(result)
        
        # Progress indicator
        status_icon = "[OK]" if not result['review_required'] else "[REVIEW]"
        print(f"  {status_icon} Case ID: {str(result['case_id'] or 'N/A'):<15} | "
              f"Type: {str(result['model_type'] or 'N/A'):<20} | "
              f"Time: {result['total_time_ms']:.1f}ms")
    
    total_time = time.time() - total_start
    
    # Write CSV report
    fieldnames = [
        'file_name', 'file_path', 'file_size_mb',
        'case_id', 'artifact_type', 'artifact_confidence', 'artifact_reasons', 'workflow',
        'model_type', 'preset', 'confidence', 'status',
        'review_required', 'review_reason',
        'dimension_x_mm', 'dimension_y_mm', 'dimension_z_mm',
        'volume_ml',
        'structure', 'structure_confidence', 'structure_reason', 'fill_ratio',
        'thickness_p10_mm', 'thickness_p50_mm', 'thin_fraction_under_5mm',
        'dimensions_time_ms', 'volume_time_ms', 'classification_time_ms',
        'structure_time_ms', 'total_time_ms',
        'error'
    ]
    
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\n{'='*80}")
    print(f"REPORT SUMMARY")
    print(f"{'='*80}")
    
    # Calculate statistics
    total_files = len(results)
    auto_classified = sum(1 for r in results if not r['review_required'])
    needs_review = sum(1 for r in results if r['review_required'])
    auto_rate = (auto_classified / total_files * 100) if total_files > 0 else 0
    
    # Timing stats
    times = [r['total_time_ms'] for r in results if r['total_time_ms']]
    avg_time = sum(times) / len(times) if times else 0
    min_time = min(times) if times else 0
    max_time = max(times) if times else 0
    
    # Cache stats
    cache = get_cache()
    cache_stats = {
        'dimensions_cached': len(cache._dimensions_cache),
        'volume_cached': len(cache._volume_cache),
        'thickness_cached': len(cache._thickness_cache),
    }
    
    # Model type distribution
    model_types = {}
    for r in results:
        mt = r['model_type'] or 'Unknown'
        model_types[mt] = model_types.get(mt, 0) + 1
    
    print(f"Total Files Processed: {total_files}")
    print(f"Auto-Classified:       {auto_classified} ({auto_rate:.1f}%)")
    print(f"Needs Review:          {needs_review}")
    print(f"")
    print(f"Processing Time:")
    print(f"  Total:               {total_time:.2f}s")
    print(f"  Average per file:    {avg_time:.1f}ms ({avg_time/1000:.2f}s)")
    print(f"  Fastest:             {min_time:.1f}ms")
    print(f"  Slowest:             {max_time:.1f}ms")
    print(f"")
    print(f"Cache Statistics:")
    print(f"  Dimensions cached:   {cache_stats['dimensions_cached']}")
    print(f"  Volume cached:       {cache_stats['volume_cached']}")
    print(f"  Thickness cached:    {cache_stats['thickness_cached']}")
    print(f"")
    print(f"Model Type Distribution:")
    for mt, count in sorted(model_types.items()):
        print(f"  {mt:<25} {count} ({count/total_files*100:.1f}%)")
    print(f"")
    print(f"Output CSV: {output_csv}")
    print(f"{'='*80}\n")
    
    return {
        'total_files': total_files,
        'auto_classified': auto_classified,
        'needs_review': needs_review,
        'auto_rate': auto_rate,
        'total_time_s': total_time,
        'avg_time_ms': avg_time,
        'min_time_ms': min_time,
        'max_time_ms': max_time,
        'cache_stats': cache_stats,
        'model_types': model_types,
        'output_csv': str(output_csv),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/classify_batch.py <input_directory> [output_csv]")
        print("\nExample:")
        print('  python scripts/classify_batch.py "D:\\Marcus\\Desktop\\BM\\20260409_Andent_Matt\\Test Data 2" report.csv')
        sys.exit(1)
    
    input_dir = Path(sys.argv[1])
    
    if not input_dir.exists():
        print(f"Error: Directory not found: {input_dir}")
        sys.exit(1)
    
    # Find all STL files
    stl_files = sorted(input_dir.glob("*.stl"))
    
    if not stl_files:
        print(f"No STL files found in: {input_dir}")
        sys.exit(1)
    
    # Output CSV path
    if len(sys.argv) >= 3:
        output_csv = Path(sys.argv[2])
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = input_dir / f"classification_report_{timestamp}.csv"
    
    # Generate report
    summary = generate_report(stl_files, output_csv)
    
    # Return summary as JSON for potential API use
    import json
    summary_json = {
        'success': True,
        'summary': summary,
    }
    
    # Write JSON summary
    json_path = output_csv.with_suffix('.json')
    with open(json_path, 'w') as f:
        json.dump(summary_json, f, indent=2)
    
    print(f"JSON Summary: {json_path}\n")
    
    return summary


if __name__ == "__main__":
    main()
