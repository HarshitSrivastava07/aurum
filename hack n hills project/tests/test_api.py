import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.models import ResearchConfig
from backend.services.red_team import audit
from backend.services.analytics import analyze_pair
from backend.services.replay import replay
from tests.test_financial import market_fixture, CONFIG


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path/'data',tmp_path/'evidence'))


def test_api_empty_data_returns_honest_certificate_and_reproduces(client):
    assert client.get('/health').json()['status']=='ok'
    assert client.get('/api/summary').json()['rows']==0
    response=client.post('/api/investigations',json={})
    assert response.status_code==200, response.text
    cert=response.json()
    assert cert['verdict']=='INSUFFICIENT EVIDENCE'
    assert cert['sources']==[]
    assert cert['outputs']['replay']['trades']==[]
    reproduction=client.post(f"/api/investigations/{cert['id']}/reproduce")
    assert reproduction.status_code==200, reproduction.text
    assert reproduction.json()['match']
    assert len(client.get('/api/investigations').json())==1


def test_daily_import_database_engine_and_export(client):
    frame=market_fixture(65)
    # This independent fixture is a test artifact, explicitly stored as synthetic.
    csv=frame.to_csv(index=False).encode()
    imported=client.app.state.storage.import_bytes('synthetic_test.csv',csv,mode='synthetic')
    assert imported['rows_imported']==130, imported
    body={**CONFIG,'start':'2025-01-02','cutoff':frame.date.max(),'end':frame.date.max(),'window':10}
    for endpoint in ['analytics','curves','ghost','analogs','replay','audit']:
        response=client.post('/api/'+endpoint,json=body)
        assert response.status_code==200,(endpoint,response.text)
    response=client.post('/api/investigations',json=body)
    assert response.status_code==200,response.text
    cert=response.json()
    assert cert['data_quality']['snapshot_rows']==130
    assert len(cert['outputs']['red_team']['checks'])==21
    assert cert['mode_label'].startswith('SYNTHETIC')
    saved=client.get('/api/investigations/'+cert['id']).json()
    assert saved['result_hash']==cert['result_hash']
    rerun=client.post('/api/investigations/'+cert['id']+'/reproduce')
    assert rerun.status_code==200,rerun.text
    assert rerun.json()['match']
    assert client.get('/api/summary?mode=real').json()['rows']==0


def test_invalid_inputs_path_and_zip_are_blocked(client):
    assert client.post('/api/replay',json={'execution_delay':0}).status_code==422
    assert client.post('/api/ghost',json={'simulations':10000000}).status_code==422
    assert client.post('/api/analytics',json={'pair':['GOLDM','GOLDM']}).status_code==422
    assert client.get('/api/investigations/not-a-uuid').status_code==422
    assert client.get('/api/data?limit=999999999').status_code==422
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        z.writestr('../escape.csv','Symbol,Date\nGOLDM,2025-01-02')
    reply=client.post('/api/import',files=[('files',('unsafe.zip',output.getvalue(),'application/zip'))])
    assert reply.status_code==200
    assert reply.json()['reports'][0]['status']=='rejected'


def test_adversarial_checks_detect_injected_execution_and_accounting_defects():
    frame=market_fixture()
    config={**CONFIG,'cutoff':frame.date.max()}
    a=analyze_pair(frame,config)
    result=replay(frame,config)
    assert result['trades'], 'Fixture must exercise actual fills'
    result['trades'][0]['entry_date']=result['trades'][0]['signal_date']
    result['trades'][0]['lots_a']=0.5
    result['trades'][0]['net_pnl']+=100000
    report=audit(frame,config,a,result)
    status={r['attack_id']:r['status'] for r in report['checks']}
    assert status['SAME_DAY']=='fail'
    assert status['INTEGER']=='fail'
    assert status['ATTRIBUTION']=='fail'


def test_snapshot_tampering_refuses_reproduction(client):
    cert=client.post('/api/investigations',json={}).json()
    path=client.app.state.ledger.directory(cert['id'])/'certificate.json'
    text=path.read_text(encoding='utf-8').replace(cert['snapshot_hash'],'0'*64)
    path.write_text(text,encoding='utf-8')
    reply=client.post('/api/investigations/'+cert['id']+'/reproduce')
    assert reply.status_code==422
    assert 'hash mismatch' in reply.json()['detail']
