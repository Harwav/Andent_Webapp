import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.andent_service_pipeline import PipelineEventHandler, NullEventHandler, PipelineJobConfig, PipelineResult, HeadlessPipeline

def test_null_event_handler_satisfies_protocol():
    handler = NullEventHandler()
    handler.update_status("hello")
    handler.show_error("title", "msg")
    handler.show_warning("title", "msg")
    handler.set_stage("Arrange")
    handler.reset_batch_progress(5)
    handler.set_batch_progress_value(3)
    handler.update_overall_progress(10)
    handler.processing_finished(5, 1.2, [], 0)
    handler.show_stages(skip_export=False, skip_print=False)
    handler.add_result_to_list({})
    handler.update_latest_result({})
    handler.record_batch_completion(5, 1.2)
    handler.update_folder_status("/tmp/foo", "Processing...")
    choice = handler.show_validation_dialog({})
    assert choice == "continue"
    handler.complete_stages()
    handler.hide_stages()
    handler.auto_save_detailed_report([], "name")


def test_pipeline_job_config_defaults():
    cfg = PipelineJobConfig(
        folders_to_process=["/tmp/stls"],
        api_payload={"material_code": "DENTAL-LT"},
        print_settings_for_manifest={"printer_name": "Form 4"},
        selected_printer_ids=["printer-1"],
    )
    assert cfg.save_only is False
    assert cfg.save_form_files is False


def test_pipeline_result_defaults():
    result = PipelineResult(processed_count=3, resin_saved_ml=4.5, skipped_files=[], manual_review_items=[])
    assert result.artifact_paths == []
    assert result.error is None


class _StubSettings:
    def get(self, key, default=None):
        return {
            'output': '/tmp/andent_test_output',
            'save_form_files': False,
            'workflow_mode': 'standard',
        }.get(key, default)

class _StubApi:
    pass

class _StubLocalController:
    pass

def test_headless_pipeline_instantiates():
    pipeline = HeadlessPipeline(
        settings_manager=_StubSettings(),
        api_client=_StubApi(),
        event_handler=NullEventHandler(),
        local_controller=_StubLocalController(),
    )
    assert hasattr(pipeline, 'run')


from app.services.prep_pipeline import WebEventHandler, collect_events

def test_web_event_handler_collects_events():
    events = []
    handler = WebEventHandler(events)
    handler.update_status("processing batch 1")
    handler.show_error("Scene Error", "Could not create scene")
    handler.processing_finished(3, 2.1, ["bad.stl"], 0)
    assert len(events) == 3
    assert events[0] == {"type": "status", "message": "processing batch 1"}
    assert events[1] == {"type": "error", "title": "Scene Error", "message": "Could not create scene"}
    assert events[2]["type"] == "finished"
    assert events[2]["processed"] == 3


import tempfile

def test_headless_pipeline_no_stl_files_exits_cleanly():
    with tempfile.TemporaryDirectory() as tmpdir:
        events = []
        handler = WebEventHandler(events)
        pipeline = HeadlessPipeline(
            settings_manager=_StubSettings(),
            api_client=_StubApi(),
            event_handler=handler,
            local_controller=_StubLocalController(),
        )
        job = PipelineJobConfig(
            folders_to_process=[tmpdir],
            api_payload={"material_code": "DENTAL-LT"},
            print_settings_for_manifest={"printer_name": "Form 4"},
            selected_printer_ids=[],
        )
        result = pipeline.run(job)

    event_types = [e["type"] for e in events]
    assert "error" in event_types or "status" in event_types
    assert result.processed_count == 0
