import pytest
from hypothesis import given, strategies as st
from backend.models import ResearchConfig
from backend.services.costs import cost_components, fill_cost
from backend.services.genome import integer_hedge
from backend.services.replay import replay,leg_pnl
from tests.test_financial import MINI,TEN,market_fixture,CONFIG


def test_independent_effective_dated_component_fees():
    c={'slippage_bps':2,'cost_schedule':[
        {'schedule_id':'before','effective_from':'2025-01-01','effective_to':'2025-06-30','brokerage_per_lot':20,'exchange_bps':1,'regulatory_bps':.1,'sell_tax_bps':1,'gst_fraction':.18},
        {'schedule_id':'after','effective_from':'2025-07-01','brokerage_per_lot':30,'exchange_bps':2}]}
    result=cost_components('2025-06-30',100000,-2,MINI,c)
    assert result['turnover']==2000000
    assert result['brokerage']==40
    assert result['exchange']==200
    assert result['regulatory']==20
    assert result['transaction_taxes']==200
    assert result['gst']==pytest.approx(46.8)
    assert result['slippage']==400
    assert fill_cost('2025-06-30',100000,-2,MINI,c)==pytest.approx(906.8)
    assert cost_components('2025-07-01',100000,2,MINI,c)['schedule_id']=='after'
    with pytest.raises(ValueError,match='cover'):
        fill_cost('2024-01-01',100000,2,MINI,c)


def test_overlap_rejected_and_dated_costs_reconcile_replay():
    with pytest.raises(ValueError,match='overlap'):
        ResearchConfig(cost_schedule=[{'schedule_id':'a','effective_from':'2025-01-01'},{'schedule_id':'b','effective_from':'2025-02-01'}])
    result=replay(market_fixture(),{**CONFIG,'cost_schedule':[{'schedule_id':'assumed','effective_from':'2025-01-01','brokerage_per_lot':20,'exchange_bps':1}]})
    assert result['trades']
    for t in result['trades']:
        fees=sum(v for key in ('entry_cost_breakdown','exit_cost_breakdown') for component in t[key].values() for name,v in component.items() if name not in ('turnover','schedule_id'))
        assert t['costs']==pytest.approx(fees)
        assert t['gross_pnl']-fees==pytest.approx(t['net_pnl'])


@given(st.integers(1,100),st.floats(1000,1000000,allow_nan=False,allow_infinity=False),st.floats(-500,500,allow_nan=False,allow_infinity=False))
def test_signed_lot_pnl_is_antisymmetric(lots,entry,change):
    assert leg_pnl(entry,entry+change,lots,MINI)==-leg_pnl(entry,entry+change,-lots,MINI)


def test_full_policy_rejection_is_recorded_and_does_not_train_on_future():
    frame=market_fixture(80)
    cfg={**CONFIG,'baseline':'C','cutoff':'2025-03-20'}
    run=replay(frame,cfg)
    assert any(e['type']=='candidate_rejected' for e in run['events'])
    frame.loc[frame.date>cfg['cutoff'],'close']*=50
    assert replay(frame,cfg)==run
