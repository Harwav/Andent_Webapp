from scripts.validate_launch import has_scene_dispatch_evidence, select_dispatch_row_ids


def test_select_dispatch_row_ids_prefers_same_case_ready_group():
    upload_result = {
        "rows": [
            {"row_id": 1, "case_id": "CASE-A", "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-B", "status": "Ready"},
            {"row_id": 3, "case_id": "CASE-B", "status": "Ready"},
            {"row_id": 4, "case_id": "CASE-C", "status": "Needs Review"},
        ]
    }

    assert select_dispatch_row_ids(upload_result) == [2, 3]


def test_select_dispatch_row_ids_falls_back_to_first_ready_row():
    upload_result = {
        "rows": [
            {"row_id": 1, "case_id": "CASE-A", "status": "Needs Review"},
            {"row_id": 2, "case_id": "", "status": "Ready"},
        ]
    }

    assert select_dispatch_row_ids(upload_result) == [2]


def test_has_scene_dispatch_evidence_requires_scene_id():
    assert has_scene_dispatch_evidence({"jobs": [{"scene_id": "scene-123"}]}) is True
    assert has_scene_dispatch_evidence({"jobs": [{"scene_id": None}]}) is False
    assert has_scene_dispatch_evidence({"jobs": []}) is False
