"""Batch import explicitly supplied files, preserving all per-file outcomes."""
import argparse
import json
from pathlib import Path
from backend.services.storage import Storage

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--date-order', choices=['mdy','dmy'], default='mdy')
    parser.add_argument('--requested-date', help='DD/MM/YYYY, separate from the returned Date convention')
    args = parser.parse_args()
    store = Storage(args.data_dir)
    for path in args.files:
        report = store.import_bytes(path.name, path.read_bytes(),args.requested_date,args.date_order)
        print(json.dumps({k: report.get(k) for k in ['filename','status','rows_imported','rows_rejected','duplicate_source','code','error','source_hash','profile']},ensure_ascii=True))
