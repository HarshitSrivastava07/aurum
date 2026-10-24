"""Regression counterexamples found during independent quantitative review."""
from copy import deepcopy
import pandas as pd
from backend.services.analytics import analyze_pair
from backend.services.red_team import audit
from backend.services.orchestration import determine_verdict
from backend.services.scenarios import ghost_market,survival_map,REQUIRED_SCENARIOS
from backend.services.replay import replay
from tests.test_financial import CONFIG,market_fixture


def complete_evidence_fixture():
    # Decision-policy fixture only, not a fabricated market research record.
    return {'red_team':{'summary':{'pass':21,'fail':0,'not-evaluable':0}},
            'mirage':{'latest':{'candidate':True}},
            'replay':{'holdout':{'trades':30,'net_pnl':100},'open_position':None},
            'ghost':{'status':'simulated','scenarios':[{'name':name,'status':'modeled_only','lifecycle_eligible':True,'liquidity_eligible':True,'median_net_pnl':1} for name in REQUIRED_SCENARIOS]}}


def test_critical_failure_overrides_unrelated_unresolved_evidence():
    evidence=complete_evidence_fixture()
    assert determine_verdict(evidence)=='SURVIVES MODELED TESTS'
    evidence['red_team']['summary'].update(fail=1,**{'not-evaluable':5})
    assert determine_verdict(evidence)=='REJECTED'


def test_missing_or_execution_blocked_stress_cannot_survive():
    for status in ('insufficient_data','no_feasible_integer_hedge'):
        evidence=complete_evidence_fixture()
        evidence['ghost']={'status':status,'scenarios':[]}
        assert determine_verdict(evidence)=='INSUFFICIENT EVIDENCE'
    evidence=complete_evidence_fixture()
    evidence['ghost']['scenarios'][0]['status']='financial_scenario_execution_blocked'
    assert determine_verdict(evidence)=='INSUFFICIENT EVIDENCE'
    evidence=complete_evidence_fixture()
    evidence['replay']['open_position']={'unrealized_loss':-1000}
    assert determine_verdict(evidence)=='INSUFFICIENT EVIDENCE'


def test_future_probe_is_a_separate_audit_fixture_not_market_data():
    frame=market_fixture(50)
    original=frame.copy(deep=True)
    cfg={**CONFIG,'cutoff':frame.date.max()}
    before=analyze_pair(frame,cfg)
    result=audit(frame,cfg,before)
    future=next(c for c in result['checks'] if c['attack_id']=='FUTURE')
    assert future['status']=='pass'
    assert future['input_evidence']['audit_only_synthetic_probe_rows']==2
    assert future['input_evidence']['positive_control_changed']
    assert not future['input_evidence']['probe_is_market_history']
    pd.testing.assert_frame_equal(frame,original)
    assert analyze_pair(frame,cfg)==before


def test_common_percentage_stress_uses_money_exposure_not_fine_grams():
    frame=market_fixture()
    latest=frame.date.max()
    frame.loc[(frame.date==latest)&(frame.symbol=='GOLDM'),'close']*=1.02
    result=ghost_market(frame,CONFIG)
    scenarios={s['name']:s for s in result['scenarios']}
    assert scenarios['Correlated adverse movements']['mean_net_pnl']<scenarios['Base paired bootstrap']['mean_net_pnl']


def test_future_probe_needs_both_contracts_after_cutoff():
    frame=market_fixture(50)
    cutoff=frame.date.max()
    frame.loc[frame.symbol=='GOLDM','expiry']=cutoff
    cfg={**CONFIG,'cutoff':cutoff}
    result=audit(frame,cfg,analyze_pair(frame,cfg))
    future=next(c for c in result['checks'] if c['attack_id']=='FUTURE')
    assert future['status']=='not-evaluable'
    assert future['input_evidence']['audit_only_synthetic_probe_rows']==0


def test_profitable_closed_trades_do_not_hide_open_position_loss():
    frame=market_fixture(118)
    frame['open']=frame.groupby('symbol')['close'].shift(1).fillna(frame['close'])
    latest=frame.date.max()
    frame.loc[(frame.date==latest)&(frame.symbol=='GOLDM'),'close']*=1.2
    cfg={**CONFIG,'baseline':'B','cost_bps':0,'end':'2025-06-18'}
    result=replay(frame,cfg)
    assert result['metrics']['net_pnl']>0
    assert result['metrics']['total_equity_change']<0
    assert result['open_position']
    sensitivity=survival_map(frame,cfg)
    cell=next(c for c in sensitivity['cells'] if c['cost_bps']==0 and c['execution_delay']==1)
    assert not cell['survives']
    assert cell['evaluation_status']=='not-evaluable'
