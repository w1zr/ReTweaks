from rt_navigation import GROUPS, NAV, group_for_index, preferred_section, GROUP_ALIASES
import rt_sidebar


def test_every_original_page_has_a_visible_group_or_direct_entry():
    original={name for _,items in rt_sidebar.LEGACY_NAV for name,_ in items}
    sections=[alias for children in GROUPS.values() for _,alias,_ in children]
    direct={name for _,items in NAV for name,_ in items}
    assert original<=set(sections)|direct|{'Backgrounds'}
    assert len(sections)==len(set(sections))
    assert sum(len(items) for _,items in NAV)==19
    assert sum(len(items) for _,items in rt_sidebar.LEGACY_NAV for _ in [0])>45


def test_tweaks_and_benchmarks_are_combined_without_reindexing():
    assert {target for _,_,target in GROUPS['Tweaks & presets']}=={1,2,10,15,17}
    assert [target for _,_,target in GROUPS['Benchmark & FPS']]==[8,'FPS overlay','Snapshots']
    class Hub:
        rt_tabs={'FPS overlay':33,'Snapshots':42}
    assert group_for_index(Hub(),8)=='Benchmark & FPS'
    assert group_for_index(Hub(),33)=='Benchmark & FPS'
    assert group_for_index(Hub(),2)=='Tweaks & presets'


def test_renamed_groups_keep_old_section_preferences_and_have_content_labels():
    saved={'navigation_sections':{'Tweaks':'CTT library','PC builder':'Bottleneck'}}
    assert preferred_section(saved,'Tweaks & presets')=='CTT library'
    assert preferred_section(saved,'PC planning')=='Bottleneck'
    assert all(new in GROUPS for new in GROUP_ALIASES.values())
    restored={'Drivers','File Transfers','Backgrounds','App Starter'}
    nested={alias for children in GROUPS.values() for _,alias,_ in children}
    assert not restored & nested
