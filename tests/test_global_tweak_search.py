from types import SimpleNamespace
from unittest.mock import Mock
from rt_search import GlobalSearch


def searcher(tweaks):
    sidebar=SimpleNamespace(targets={'Individual tweaks':1},primary_names=['Individual tweaks'],open=Mock())
    hub=SimpleNamespace(sidebar_nav=sidebar,rt_pages={})
    search=GlobalSearch.__new__(GlobalSearch)
    search.hub=hub;search.g={'TWEAKS':tweaks}
    return search


def test_exact_tweak_is_not_lost_after_first_eight_description_matches():
    tweaks=[{'name':'Other option '+str(i),'desc':'Disable telemetry is mentioned here','cat':'System'} for i in range(20)]
    tweaks.append({'name':'Disable telemetry','desc':'Control diagnostics','cat':'System'})
    search=searcher(tweaks)
    results=search.search('disable telemetry')
    assert results[0][0]=='Disable telemetry'
    assert results[0][1]=='Tweak · Individual tweaks'


def test_tweak_result_opens_filtered_list_without_applying_or_selecting():
    search=searcher([{'name':'Disable core parking','desc':'CPU responsiveness','cat':'System'}])
    search.hub.show_tab=Mock();search.hub.show_tweaks_tab=Mock();search.hub.tweak_search=Mock()
    result=search.search('cpu parking')[0]
    result[2]()
    search.hub.show_tab.assert_called_once_with(1)
    search.hub.show_tweaks_tab.assert_called_once_with('all')
    search.hub.tweak_search.set.assert_called_once_with('Disable core parking')
