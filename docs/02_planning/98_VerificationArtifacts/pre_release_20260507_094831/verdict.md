SHIP: yes

# Release Gate Verdict

- Git commit: `1c214c2e41621693a3a48c572cea02a522e0b3e7`
- Dataset: `C:\Users\Marcus\Desktop\From 4BL Test Data`
- STL count: `91`
- PreForm URL: `http://127.0.0.1:44388`

| Stage | Status | Duration | Artifacts |
| --- | --- | ---: | --- |
| environment | pass | 1.41s | `dataset-manifest.json`, `preform-status.json`, `git-status.txt` |
| static | pass | 0.10s | `python-compile.log` |
| backend | pass | 24.72s | `pytest.log` |
| browser-mocked | pass | 75.26s | `browser-mocked.log` |
| browser-live-app | pass | 43.47s | `browser-live-app.log` |
| live-preform-virtual | pass | 48.49s | `live-preform-virtual.log` |
| packaged-runtime | pass | 11.46s | `packaged-runtime.log` |
