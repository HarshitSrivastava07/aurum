"""Explicit effective-dated fee assumptions; no universal historical fee claim."""

def cost_components(day, price, lots, spec, config):
    turnover=abs(float(price)*int(lots)*spec['trading_unit_g']/spec['quotation_unit_g'])
    schedule=config.get('cost_schedule') or []
    applicable=[s for s in schedule if s['effective_from']<=str(day) and (not s.get('effective_to') or str(day)<=s['effective_to'])]
    if schedule and len(applicable)!=1:
        raise ValueError('Exactly one cost schedule must cover each modeled fill date')
    if not applicable:
        return {'assumed_all_in':turnover*config.get('cost_bps',5)/10000,
                'slippage':turnover*config.get('slippage_bps',2)/10000,
                'turnover':turnover,'schedule_id':'aggregate-assumption'}
    s=applicable[0]
    brokerage=abs(int(lots))*s.get('brokerage_per_lot',0)
    exchange=turnover*s.get('exchange_bps',0)/10000
    regulatory=turnover*s.get('regulatory_bps',0)/10000
    gst=(brokerage+exchange+regulatory)*s.get('gst_fraction',0)
    tax=turnover*s.get('buy_tax_bps' if lots>0 else 'sell_tax_bps',0)/10000
    return {'brokerage':brokerage,'exchange':exchange,'regulatory':regulatory,'gst':gst,'transaction_taxes':tax,
            'additional_penalty':abs(int(lots))*s.get('extra_per_lot',0),
            'slippage':turnover*config.get('slippage_bps',2)/10000,'turnover':turnover,'schedule_id':s['schedule_id']}


def fill_cost(day,price,lots,spec,config):
    breakdown=cost_components(day,price,lots,spec,config)
    return sum(value for name,value in breakdown.items() if name not in {'turnover','schedule_id'})
