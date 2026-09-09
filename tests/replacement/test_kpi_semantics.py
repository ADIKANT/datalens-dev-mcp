import json
import subprocess
from importlib.resources import files

import pytest

from datalens_dev_mcp.authoring.recipes import compile_recipe, list_recipes


def render(value, previous, **semantics):
    config = list_recipes()['kpi_sparkline']['visual_contract']
    config['kpi'].update(semantics)
    config['labels'].update(unit='%' if semantics.get('value_scale') else 'ms', precision=1)
    data = {'value': value, 'previous': previous, 'points': [{'date': 'day', 'value': value}]}
    source = files('datalens_dev_mcp.assets.recipes').joinpath('kpi_sparkline_renderer.js').read_text()
    script = "const vm=require('node:vm'); const Editor={wrapFn:x=>x,generateHtml:x=>x};" + source
    script += '\nconst r=module.exports('+json.dumps(data)+','+json.dumps(config)+');'
    script += "const invoke=(w,e)=>vm.runInNewContext('('+w.fn.toString()+')',{Editor})(e,...w.args);"
    script += "console.log(JSON.stringify({body:invoke(r.render,{width:300,height:180}),tooltip:invoke(r.tooltip.renderer,{target:{getAttribute:()=> 'kpi-delta'}})}));"
    return json.loads(subprocess.check_output(['node','-e',script],text=True))


@pytest.mark.parametrize('current,previous,direction,color', [(240,200,'lower_is_better','#B3261E'),(200,240,'lower_is_better','#0B8043'),(120,100,'higher_is_better','#0B8043'),(120,100,'neutral','#5F6368')])
def test_direction(current, previous, direction, color):
    assert 'color:'+color in render(current,previous,direction=direction)['body']


@pytest.mark.parametrize('current,previous,scale',[(84,80,'percent'),(.84,.8,'fraction')])
@pytest.mark.parametrize('kind,text',[('percentage_points','+4 pp'),('relative','+5%')])
def test_percentage(current,previous,scale,kind,text):
    result=render(current,previous,value_scale=scale,delta_kind=kind)
    assert text in result['body'] and text in result['tooltip']
    assert '84.0' in result['body'] and '80.0 %' in result['tooltip']


def test_units_raw_precision_and_baselines():
    result=render(240.12345,200,delta_kind='absolute')
    assert '+40.1 ms' in result['body'] and '240.12345 ms' in result['tooltip']
    for previous in (0,None):
        result=render(10,previous)
        assert 'n/a' in result['body']
        assert 'Infinity' not in str(result)
    assert '+50%' in render(-10,-20)['body']
    assert '+10.0 ms' in render(10,0,delta_kind='absolute')['body']


def test_binding_semantics_and_reference_priority(tmp_path):
    bindings={'metric':{'label':'orders','direction':'lower_is_better'},'date':{},'comparison':{},'prepared_data':{'value':120,'previous':100,'points':[]}}
    draft=compile_recipe('kpi_sparkline',bindings,reference={'kpi':{'direction':'higher_is_better'}},user_config_path=tmp_path/'none')['draft']
    assert draft['config']['kpi']['direction']=='higher_is_better'
    assert compile_recipe('kpi_sparkline',bindings,user_config_path=tmp_path/'none')['draft']['config']['kpi']['direction']=='lower_is_better'
    bindings['metric']={'label':'orders'}
    assert compile_recipe('kpi_sparkline',bindings,user_config_path=tmp_path/'none')['draft']['config']['kpi']['direction']=='neutral'
    with pytest.raises(ValueError,match='direction'):
        compile_recipe('kpi_sparkline',bindings,presentation={'kpi':{'direction':'guess'}},user_config_path=tmp_path/'none')


def test_fraction_raw_value_keeps_its_scale():
    result = render(.84, .8, value_scale='fraction')
    assert '0.84 (fraction)' in result['tooltip']
    assert '0.84 %' not in result['tooltip']


def test_profile_reference_and_explicit_priority(tmp_path):
    user = tmp_path / 'authoring.json'
    user.write_text(json.dumps({'families': {'kpi_sparkline': {'kpi': {'direction': 'higher_is_better'}}}}))
    bindings = {'metric': {'direction': 'neutral'}, 'date': {}, 'comparison': {}, 'prepared_data': {'value': 120, 'previous': 100, 'points': []}}
    def contract(**kwargs):
        return compile_recipe('kpi_sparkline', bindings, user_config_path=user, **kwargs)['draft']['config']['kpi']
    assert contract()['direction'] == 'higher_is_better'
    assert contract(reference={'kpi': {'direction': 'lower_is_better'}})['direction'] == 'lower_is_better'
    assert contract(reference={'kpi': {'direction': 'lower_is_better'}}, presentation={'kpi': {'direction': 'neutral'}})['direction'] == 'neutral'
