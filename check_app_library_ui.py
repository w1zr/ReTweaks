"""100-app browsing and error help UI with simulated failures/AI only."""
import json,time
from unittest.mock import Mock,patch
import automation
import app_starter
import retweaks as app
import hubplus
from app_troubleshooting import failure_record

class Hotkeys:
    def __init__(self,*args):self.thread=Mock()
    def update(self,*args):pass
    def close(self):pass
automation.Hotkeys=Hotkeys
app.Hub._load_info=lambda self:None
hubplus.write_json=lambda *args:None
hubplus.install(vars(app))
hub=app.Hub(show_intro=False,enable_ai=False)
errors=[];hub.report_callback_exception=lambda *args:errors.append(args)
def pump():
    for _ in range(12):hub.update();time.sleep(.025)
try:
    hub.show_tab(23);pump();page=hub.app_starter
    assert len(page.choices)==100 and len(page.visible)==100 and len(page.rows)==100
    page.choices['chrome'].set(True);assert page.choices['chrome'].get()
    assert len(page.cards)==100 and all(page.logos.values())
    original_cards={key:item['card'] for key,item in page.cards.items()}
    canvas=page.grid.master.master
    assert canvas.winfo_class()=='Canvas'
    canvas.yview_moveto(1);pump()
    last=page.cards[page.visible[-1]]['card']
    assert last.winfo_rooty()+last.winfo_height()>canvas.winfo_rooty()
    assert last.winfo_rooty()<canvas.winfo_rooty()+canvas.winfo_height()
    assert canvas.yview()[1]>.999
    # Native windows may report a clipped height while rapidly scrolling.
    # A clipped child must never resize the complete card or scroll region.
    from types import SimpleNamespace
    before={key:int(item['card'].cget('height')) for key,item in page.cards.items()}
    region=canvas.cget('scrollregion')
    for item in page.cards.values():item['card']._on_body(SimpleNamespace(height=1))
    pump()
    assert all(int(page.cards[key]['card'].cget('height'))==height for key,height in before.items())
    assert canvas.cget('scrollregion')==region
    for fraction in (0,.9,.1,1,.3,.8,0,1)*5:
        canvas.yview_moveto(fraction);hub.update()
        assert all(int(page.cards[key]['card'].cget('height'))==height for key,height in before.items())
    page.toggle_details('ubisoft');pump()
    assert int(last.cget('height'))>before['ubisoft']
    page.toggle_details('ubisoft');pump()
    assert int(last.cget('height'))==before['ubisoft']

    canvas.yview_moveto(.12);pump()
    from PIL import Image,ImageDraw
    sheet=Image.new('RGB',(1000,1300),'#161b22');draw=ImageDraw.Draw(sheet)
    for i,(key,record) in enumerate(app_starter.APPS.items()):
        with Image.open('assets/apps/'+key+'.png') as image:
            image=image.convert('RGBA');image.thumbnail((64,64),Image.Resampling.LANCZOS)
            x=(i%10)*100;y=(i//10)*130;sheet.paste(image,(x+(100-image.width)//2,y+10),image)
            draw.text((x+4,y+82),key,fill='white')
    sheet.save('verification/all-app-artwork.jpg')
    canvas.yview_moveto(0)

    page.search.set('Mozilla Firefox');pump();assert page.visible==['firefox'] and len(page.rows)==1
    page.choices['firefox'].set(True);started=time.perf_counter();page.browse_all();print(f'Cached 100-card refresh: {time.perf_counter()-started:.3f}s');assert page.choices['firefox'].get() and page.choices['chrome'].get()
    page.category.set('Creative');page.filter_apps();assert all(app_starter.APPS[k][2]=='Creative' for k in page.visible)
    page.category.set('All categories');page.search.set('no such app 000');page.filter_apps();assert not page.rows
    page.search.set('');page.filter_apps();page.clear();page.select_shown();assert sum(v.get() for v in page.choices.values())==100
    page.preset('Gaming');assert page.visible==list(app_starter.PRESETS['Gaming'])
    assert len(page.rows)==len(app_starter.PRESETS['Gaming'])
    assert all(page.cards[key]['card'] is card for key,card in original_cards.items())
    report=failure_record('chrome',app_starter.APPS['chrome'],'download','Network download interrupted',0x8A150008,'No private data')
    page.events.put(('failure','chrome',report));pump();assert 'chrome' in page.failures
    page.help_failure('chrome');pump();info=page.help_windows['chrome']
    assert 'download' in info['text'].get('1.0','end') and info['window'].winfo_exists()
    # Download help must not accidentally install when the global mode is Install.
    page.mode.set('Install apps')
    with patch.object(page.runner,'start',return_value=False) as start:
        page.start_keys(['chrome'],report['mode']);assert start.call_args.args==(['chrome'],'download')
    page.failures['chrome']=report;hub.enable_ai=True
    with patch('drivers.ask_ai',return_value={'text':json.dumps({'summary':'Server unavailable.','steps':['Retry the download.']})}) as ask:
        info['button'].command();pump()
        assert 'Server unavailable.' in info['text'].get('1.0','end')
        assert ask.call_args.args[0]['task']=='app_failure'
    page.close_help(info);assert info['token'].closed
    assert not errors,errors
finally:hub.destroy()
print('PASS: 100 apps, continuous scrolling, bundled icons and reused cards, search/categories, persistent selections, original bundles, failed-app help and advisory AI response. No downloads/installs/real AI.')
