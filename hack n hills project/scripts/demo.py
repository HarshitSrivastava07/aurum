"""Generate isolated demo data and run/reproduce a complete investigation."""
import json
from pathlib import Path
from backend.models import ResearchConfig
from backend.services.demo import create_demo
from backend.services.storage import Storage
from backend.services.ledger import Ledger
from backend.services.orchestration import investigate, reproduce

if __name__ == '__main__':
    store, ledger = Storage(Path('data')), Ledger(Path('evidence'))
    demo = create_demo(store)
    config = ResearchConfig(mode='synthetic',start='2025-01-02',end='2025-09-10',cutoff='2025-09-10',window=20,simulations=500).as_dict()
    cert = investigate(store,ledger,config)
    print(json.dumps({'demo_import':demo['import']['status'],'id':cert['id'],'verdict':cert['verdict'],'data_quality':cert['data_quality'],'replay':cert['outputs']['replay']['metrics'],'audit':cert['outputs']['red_team']['summary'],'reproduction':reproduce(ledger,cert['id'])},indent=2))
