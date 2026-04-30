import sqlite3, json, os

db_path = r'D:\Marcus\Desktop\Andent_Webapp\data\andent_web.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute(
    'SELECT job_name, estimated_density, density_target, printer_type, '
    'case_ids, manifest_json FROM print_jobs ORDER BY created_at DESC LIMIT 10'
)
rows = cur.fetchall()

print('=== PRINT JOBS (latest 10) ===')
for r in rows:
    jn = r['job_name']
    ed = r['estimated_density']
    dt = r['density_target']
    pt = r['printer_type']
    ci = r['case_ids']
    mj = r['manifest_json']
    print(f'  Job: {jn}')
    print(f'    estimated_density: {ed:.4f}')
    print(f'    density_target: {dt}')
    print(f'    printer_type: {pt}')
    manifest = json.loads(mj) if mj else {}
    if manifest:
        uxb = manifest.get('used_xy_budget', 'N/A')
        pxb = manifest.get('printer_xy_budget', 'N/A')
        print(f'    used_xy_budget: {uxb:.2f}')
        print(f'    printer_xy_budget: {pxb:.2f}')
    print()

# Get row dimensions for the latest job
if rows:
    latest = rows[0]
    case_ids = json.loads(latest['case_ids']) if latest['case_ids'] else []
    printer_type = latest['printer_type']
    print(f'=== ROW DIMENSIONS for job {latest["job_name"]} ===')
    print(f'   Case IDs: {case_ids}')
    print(f'   Printer: {printer_type}')
    print()

    total_bbox = 0.0
    total_spaced = 0.0
    row_count = 0
    full_arch_count = 0

    for cid in case_ids:
        cur.execute(
            'SELECT id, case_id, file_name, model_type, '
            'dimension_x_mm, dimension_y_mm, dimension_z_mm, preset, printer '
            'FROM upload_rows WHERE case_id = ?',
            (cid,)
        )
        row_rows = cur.fetchall()
        for rr in row_rows:
            x = rr['dimension_x_mm']
            y = rr['dimension_y_mm']
            if x is None or y is None:
                print(f'  Row {rr["id"]}: {rr["file_name"]} - NO DIMENSIONS')
                continue

            bbox = x * y
            spaced = (x + 2.0) * (y + 2.0)

            # Check full-arch
            long_side = max(x, y)
            short_side = min(x, y)
            is_full_arch = (long_side >= 190.0 and short_side >= 30.0 and x * y >= 3000.0)

            effective_bbox = bbox * 0.58 if is_full_arch else bbox
            effective_spaced = spaced * 0.58 if is_full_arch else spaced

            total_bbox += effective_bbox
            total_spaced += effective_spaced
            row_count += 1
            if is_full_arch:
                full_arch_count += 1

            print(f'  Row {rr["id"]}: {rr["file_name"]:30s} type={rr["model_type"]:6s} '
                  f'{x:7.1f} x {y:7.1f} mm  bbox={bbox:8.1f}  spaced={spaced:8.1f}  '
                  f'full_arch={is_full_arch}')

    printer_xy = 353.0 * 196.0 if printer_type == 'Form 4BL' else 200.0 * 125.0

    print()
    print(f'=== DENSITY COMPARISON for {latest["job_name"]} ===')
    print(f'   Printer: {printer_type}  Build area: {printer_xy:.0f} mm2')
    print(f'   Rows: {row_count}  Full-arch: {full_arch_count}')
    print()
    print(f'   Current formula (bbox sum / area):     {total_bbox / printer_xy:.4f}')
    print(f'   Option D (spaced * 0.82 / area):       {total_spaced * 0.82 / printer_xy:.4f}')
    print(f'   DB stored estimated_density:            {latest["estimated_density"]:.4f}')
    print()

    # Also compute for all jobs
    print('=== ALL JOBS COMPARISON ===')
    for r in rows:
        case_ids_j = json.loads(r['case_ids']) if r['case_ids'] else []
        pt = r['printer_type']
        pxy = 353.0 * 196.0 if pt == 'Form 4BL' else 200.0 * 125.0
        tb = 0.0
        ts = 0.0
        for cid in case_ids_j:
            cur.execute(
                'SELECT dimension_x_mm, dimension_y_mm FROM upload_rows WHERE case_id = ?',
                (cid,)
            )
            for rr in cur.fetchall():
                x, y = rr['dimension_x_mm'], rr['dimension_y_mm']
                if x is None or y is None:
                    continue
                long_s = max(x, y)
                short_s = min(x, y)
                is_fa = (long_s >= 190.0 and short_s >= 30.0 and x * y >= 3000.0)
                bbox = x * y * (0.58 if is_fa else 1.0)
                spaced = (x + 2.0) * (y + 2.0) * (0.58 if is_fa else 1.0)
                tb += bbox
                ts += spaced

        current = tb / pxy if pxy else 0
        option_d = (ts * 0.82) / pxy if pxy else 0
        stored = r['estimated_density']

        print(f'  {r["job_name"]:20s}  current={current:.4f}  option_d={option_d:.4f}  '
              f'stored={stored:.4f}  delta_d={option_d - current:+.4f}')

conn.close()
