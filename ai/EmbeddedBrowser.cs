using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// RETWEAKS Browser: v1.5 EmbeddedBrowser (GPL-3.0) with RETWEAKS branding and RETWEAKS'
// browser data. It runs as its own process inside the Browser page, so a browser fault never closes RETWEAKS.
// RETWEAKS additions: bookmarks/history/search-engine/download settings shared with RETWEAKS (stdin "data",
// stdout "bookmarks"/"visit"/"title"/"clear-history"/"setting"), private tabs, a Bookmarks and history page,
// clear cookies and site data, more search engines, unhandled-error guard.
class EmbeddedBrowser {
    const string Host="retweaks.internal";
    const string SettingsPage="https://retweaks.internal/browser-settings.html";
    const string Home="https://retweaks.internal/browser-home.html";
    const string Library="https://retweaks.internal/browser-library.html";
    static bool Trusted(string url){return url==Home||url==SettingsPage||url==Library;}
    [DllImport("user32.dll")] static extern IntPtr SetParent(IntPtr child,IntPtr parent);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr hwnd,int message,IntPtr wParam,string text);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr window);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] static extern bool IsChild(IntPtr parent,IntPtr child);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr window,out Rect rect);
    [DllImport("user32.dll")] static extern IntPtr GetWindowDpiAwarenessContext(IntPtr window);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    struct Rect {public int left,top,right,bottom;}
    class BrowserTab {public WebView2 view;public Panel chip;public Button title;public string url=Home;public bool busy,closed,priv;public ulong navigation;}
    class Shortcut {public string name;public string url;public string icon;}
    class IconButton:Button {
        protected override void OnPaint(PaintEventArgs e){
            if(Text.Length>1){base.OnPaint(e);return;}
            e.Graphics.Clear(BackColor);e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            float x=Width/2f,y=Height/2f;using(var pen=new Pen(Enabled?ForeColor:Color.FromArgb(90,90,97),1.7f)){
                pen.StartCap=pen.EndCap=LineCap.Round;var g=e.Graphics;
                if(Text=="←"||Text=="→"){float sign=Text=="←"?-1:1;g.DrawLine(pen,x-6,y,x+6,y);g.DrawLines(pen,new[]{new PointF(x-sign*1,y-5),new PointF(x+sign*6,y),new PointF(x-sign*1,y+5)});}
                else if(Text=="↻"){g.DrawArc(pen,x-6,y-6,12,12,35,290);g.DrawLines(pen,new[]{new PointF(x+1,y-7),new PointF(x+6,y-6),new PointF(x+5,y-1)});}
                else if(Text=="⌂"){g.DrawLines(pen,new[]{new PointF(x-7,y),new PointF(x,y-6),new PointF(x+7,y),new PointF(x+5,y),new PointF(x+5,y+6),new PointF(x-5,y+6),new PointF(x-5,y)});}
                else if(Text=="↓"){g.DrawLine(pen,x,y-7,x,y+3);g.DrawLines(pen,new[]{new PointF(x-4,y-1),new PointF(x,y+3),new PointF(x+4,y-1)});g.DrawLines(pen,new[]{new PointF(x-7,y+4),new PointF(x-7,y+7),new PointF(x+7,y+7),new PointF(x+7,y+4)});}
                else if(Text=="×"){g.DrawLine(pen,x-4,y-4,x+4,y+4);g.DrawLine(pen,x+4,y-4,x-4,y+4);}
                else if(Text=="+"){g.DrawLine(pen,x-5,y,x+5,y);g.DrawLine(pen,x,y-5,x,y+5);}
                else if(Text=="☆"||Text=="★"){var points=new PointF[10];for(int i=0;i<10;i++){double angle=(i*36-90)*Math.PI/180;float radius=i%2==0?7:3.3f;points[i]=new PointF(x+(float)Math.Cos(angle)*radius,y+(float)Math.Sin(angle)*radius);}if(Text=="★")using(var brush=new SolidBrush(pen.Color))g.FillPolygon(brush,points);else g.DrawPolygon(pen,points);}
                else{base.OnPaint(e);return;}
                if(Focused)g.DrawEllipse(pen,x-12,y-12,24,24);
            }
        }
    }
    class RoundPanel:Panel {
        public Color edge=Color.FromArgb(42,42,47);
        protected override void OnPaint(PaintEventArgs e){base.OnPaint(e);e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;using(var path=Shape(ClientRectangle,18))using(var pen=new Pen(edge)){e.Graphics.DrawPath(pen,path);}}
        protected override void OnResize(EventArgs e){base.OnResize(e);using(var path=Shape(ClientRectangle,18)){var old=Region;Region=new Region(path);if(old!=null)old.Dispose();}Invalidate();}
    }
    static GraphicsPath Shape(Rectangle r,int radius){var p=new GraphicsPath();int d=Math.Min(radius*2,Math.Min(r.Width,r.Height)-1);if(d<1){p.AddRectangle(r);return p;}p.AddArc(0,0,d,d,180,90);p.AddArc(r.Width-d-1,0,d,d,270,90);p.AddArc(r.Width-d-1,r.Height-d-1,d,d,0,90);p.AddArc(0,r.Height-d-1,d,d,90,90);p.CloseFigure();return p;}
    static JavaScriptSerializer json=new JavaScriptSerializer();
    static Form host;static IntPtr parent;static ApplicationContext loop;static CoreWebView2Environment environment;
    static FlowLayoutPanel strip;static Panel deck,chrome,bar;static TextBox address;static Label status;
    static Button back,forward,reload,star,newTab;static RoundPanel addressBox;
    static List<BrowserTab> tabs=new List<BrowserTab>();static BrowserTab active;
    static Dictionary<string,object> options=Defaults();
    static Dictionary<string,object> Defaults(){return new Dictionary<string,object>{{"homeUrl",""},{"startupUrl",""},{"showHome",true},{"showSave",true},{"showStatus",true},{"showShortcuts",true},{"compactTiles",false},{"showGreeting",true},{"showLogo",true},{"fontSize",16},{"theme","Dark"},{"scripts",true},{"contextMenus",true},{"devTools",false},{"autofill",true},{"passwords",false},{"pinchZoom",true},{"swipe",true},{"browserKeys",true},{"permissions","Ask"},{"popups",true},{"muteNewTabs",false},{"downloadPrompt",true},{"downloadFolder",""}};}
    static bool Flag(string key){return Convert.ToBoolean(options[key]);}
    static void Property(object owner,string key,object value){try{var property=owner.GetType().GetProperty(key);if(property!=null&&property.CanWrite)property.SetValue(owner,value,null);}catch{}}
    static string engine="Google";static double zoom=1;static string customSearch="";static string engineVersion="";
    static List<string> engineNames=new List<string>{"Google","Bing","DuckDuckGo"};
    static Dictionary<string,string> templates=new Dictionary<string,string>{{"Google","https://www.google.com/search?q={q}"},{"Bing","https://www.bing.com/search?q={q}"},{"DuckDuckGo","https://duckduckgo.com/?q={q}"}};
    static List<Dictionary<string,object>> history=new List<Dictionary<string,object>>();
    static bool ValidTemplate(string t){Uri u;return t!=null&&t.Length<2048&&(t.Contains("{q}")||t.Contains("%s"))&&Uri.TryCreate(t.Replace("{q}","x").Replace("%s","x"),UriKind.Absolute,out u)&&u.Scheme=="https";}
    static void SetEngine(string value){if(value!=null&&templates.ContainsKey(value)&&value!=engine){engine=value;Emit(new{type="setting",key="browser_search_engine",value=engine});}}static List<string> closedUrls=new List<string>();
    static List<Shortcut> shortcuts=new List<Shortcut>();
    static ToolTip tips=new ToolTip();
    static string AssetsPath(){string path=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","assets"));return Directory.Exists(path)?path:Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","..","assets"));}
    static string profile,prefs;static bool visible=true,closing,testing;static Color bg,panel,fg,muted,line;
    static void Emit(object data){Console.WriteLine(json.Serialize(data));Console.Out.Flush();}
    static void Status(string text){status.Text=text;}
    static Button Button(string text,int width,Control owner,Action action){var b=new IconButton{Text=text,Width=width,Height=32,FlatStyle=FlatStyle.Flat,Margin=new Padding(3),Font=new Font("Segoe UI",10),TabStop=true};string label=text=="←"?"Back":text=="→"?"Forward":text=="↻"?"Reload / stop":text=="⌂"?"Home":text=="☆"?"Save page as shortcut":text=="↓"?"Downloads":text=="+"?"New tab":text=="×"?"Close tab":text;b.AccessibleName=label;tips.SetToolTip(b,label);b.FlatAppearance.BorderSize=0;b.Resize+=(s,e)=>{using(var shape=Shape(b.ClientRectangle,16)){var old=b.Region;b.Region=new Region(shape);if(old!=null)old.Dispose();}};using(var shape=Shape(b.ClientRectangle,16))b.Region=new Region(shape);b.Click+=(s,e)=>action();owner.Controls.Add(b);return b;}
    static void Sync(){if(closing)return;bool show=visible&&IsWindowVisible(parent);host.Enabled=show;if(show&&!host.Visible)host.Show();if(!show&&host.Visible)host.Hide();Rect r;GetClientRect(parent,out r);if(host.Width!=r.right||host.Height!=r.bottom)host.SetBounds(0,0,Math.Max(1,r.right),Math.Max(1,r.bottom));}
    static bool Allowed(string text){Uri u;return Uri.TryCreate(text,UriKind.Absolute,out u)&&(u.Scheme=="https"||u.Scheme=="http");}
    public static string Destination(string text){
        text=(text??"").Trim();if(text.Length>8192)text=text.Substring(0,8192);if(text.Length==0)return Home;
        if(Allowed(text))return new Uri(text).AbsoluteUri;
        if(text.IndexOf(' ')<0 && (text.Contains(".")||text.StartsWith("localhost",StringComparison.OrdinalIgnoreCase)) && !text.Contains("://") && !text.StartsWith("javascript:",StringComparison.OrdinalIgnoreCase) && !text.StartsWith("data:",StringComparison.OrdinalIgnoreCase)){
            string candidate="https://"+text;if(Allowed(candidate))return new Uri(candidate).AbsoluteUri;
        }
        string template;if(!templates.TryGetValue(engine,out template))template="https://www.google.com/search?q={q}";string q=Uri.EscapeDataString(text);
        return template.Replace("{q}",q).Replace("%s",q);
    }
    static void SaveSettings(){try{File.WriteAllText(Path.Combine(profile,"settings.json"),json.Serialize(new{engine=engine,zoom=zoom,options=options}));}catch{Status("Preferences could not be saved.");}}
    static void LoadSettings(){try{var data=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(profile,"settings.json")));string value=Convert.ToString(data["engine"]);if(templates.ContainsKey(value))engine=value;zoom=Math.Max(.5,Math.Min(2,Convert.ToDouble(data["zoom"])));if(data.ContainsKey("options"))ReadOptions((Dictionary<string,object>)data["options"]);}catch{}}
    static void ReadOptions(Dictionary<string,object> values){foreach(var pair in values){if(!options.ContainsKey(pair.Key))continue;object original=Defaults()[pair.Key];if(original is bool&&pair.Value is bool)options[pair.Key]=pair.Value;else if(pair.Key=="fontSize"){int size=Convert.ToInt32(pair.Value);options[pair.Key]=Math.Max(12,Math.Min(24,size));}else if(original is string){string value=Convert.ToString(pair.Value);if(value.Length>2048)continue;if((pair.Key=="homeUrl"||pair.Key=="startupUrl")&&value!=""&&!Allowed(value))continue;if(pair.Key=="theme"&&value!="Dark"&&value!="Light"&&value!="System")continue;if(pair.Key=="permissions"&&value!="Ask"&&value!="Block")continue;options[pair.Key]=value;}}}
    static void ApplyOptions(){foreach(var tab in tabs){var core=tab.view.CoreWebView2;if(core==null)continue;bool trusted=Trusted(tab.url);var settings=core.Settings;settings.IsScriptEnabled=trusted||Flag("scripts");settings.AreDefaultContextMenusEnabled=Flag("contextMenus");settings.AreDevToolsEnabled=Flag("devTools");Property(settings,"IsGeneralAutofillEnabled",Flag("autofill"));Property(settings,"IsPasswordAutosaveEnabled",Flag("passwords"));Property(settings,"IsPinchZoomEnabled",Flag("pinchZoom"));Property(settings,"IsSwipeNavigationEnabled",Flag("swipe"));Property(settings,"AreBrowserAcceleratorKeysEnabled",Flag("browserKeys"));core.Profile.PreferredColorScheme=Convert.ToString(options["theme"])=="Light"?CoreWebView2PreferredColorScheme.Light:Convert.ToString(options["theme"])=="System"?CoreWebView2PreferredColorScheme.Auto:CoreWebView2PreferredColorScheme.Dark;tab.view.ZoomFactor=zoom;}
        back.Parent.Controls[3].Visible=Flag("showHome");star.Visible=Flag("showSave");status.Visible=Flag("showStatus");UpdateHomes();
    }
    static async void UpdateSettings(BrowserTab tab){if(tab.closed||tab.url!=SettingsPage||tab.view.CoreWebView2==null)return;try{await tab.view.ExecuteScriptAsync("window.renderSettings("+json.Serialize(new{engine=engine,engines=engineNames,customSearch=customSearch,version=engineVersion,zoom=zoom,options=options})+")");}catch{}}
    static void Reload(bool hard=false){if(active==null||active.view.CoreWebView2==null)return;try{if(active.busy&&!hard){active.view.CoreWebView2.Stop();active.busy=false;RefreshChrome();Status("");}else{active.busy=true;RefreshChrome();if(hard)active.view.CoreWebView2.CallDevToolsProtocolMethodAsync("Page.reload","{\"ignoreCache\":true}");else active.view.Reload();}active.view.Focus();}catch{active.busy=false;RefreshChrome();Status("Reload failed. Try reopening the tab.");}}
    static void Zoom(double value){zoom=Math.Max(.5,Math.Min(2,value));foreach(var tab in tabs)tab.view.ZoomFactor=zoom;SaveSettings();Status("Page zoom: "+Math.Round(zoom*100)+"%");}
    static void Reopen(){if(closedUrls.Count==0)return;string url=closedUrls[closedUrls.Count-1];closedUrls.RemoveAt(closedUrls.Count-1);Add(url);}
    class MenuColors:ProfessionalColorTable {
        public override Color MenuItemSelected{get{return line;}}
        public override Color MenuItemBorder{get{return line;}}
        public override Color ToolStripDropDownBackground{get{return panel;}}
        public override Color ImageMarginGradientBegin{get{return ToolStripDropDownBackground;}}
        public override Color ImageMarginGradientMiddle{get{return ToolStripDropDownBackground;}}
        public override Color ImageMarginGradientEnd{get{return ToolStripDropDownBackground;}}
        public override Color SeparatorDark{get{return line;}}
        public override Color SeparatorLight{get{return ToolStripDropDownBackground;}}
    }
    static ContextMenuStrip browserMenu;static ToolStripMenuItem settingsMenuItem;
    static ToolStripMenuItem MenuItem(string label,string shortcut,Action action){var item=new ToolStripMenuItem(label){ShortcutKeyDisplayString=shortcut,Padding=new Padding(12,7,12,7)};item.Click+=(s,e)=>{if(!closing)host.BeginInvoke((Action)(()=>{if(!closing)action();}));};return item;}
    static void Menu(Control anchor){
        if(browserMenu==null){
            browserMenu=new ContextMenuStrip{BackColor=panel,ForeColor=fg,ShowImageMargin=false,ShowCheckMargin=false,Font=new Font("Segoe UI",10),Padding=new Padding(7),Renderer=new ToolStripProfessionalRenderer(new MenuColors())};
            browserMenu.Items.Add(MenuItem("New tab","Ctrl+T",()=>Add(Home)));
            browserMenu.Items.Add(MenuItem("Reopen closed tab","Ctrl+Shift+T",Reopen));
            browserMenu.Items.Add(MenuItem("New private tab","Ctrl+Shift+N",()=>Add(Home,true)));
            browserMenu.Items.Add(new ToolStripSeparator());
            browserMenu.Items.Add(MenuItem("Reload","F5",()=>Reload()));
            browserMenu.Items.Add(MenuItem("Reload without cache","Ctrl+Shift+R",()=>Reload(true)));
            browserMenu.Items.Add(new ToolStripSeparator());
            var search=MenuItem("Search engine","",()=>{});search.DropDownItems.Add(new ToolStripMenuItem("x"));
            search.DropDownOpening+=(s,e)=>{search.DropDownItems.Clear();foreach(string choice in engineNames){string value=choice;var item=MenuItem(value,"",()=>{SetEngine(value);SaveSettings();});item.Checked=value==engine;search.DropDownItems.Add(item);}};browserMenu.Items.Add(search);
            browserMenu.Items.Add(MenuItem("Zoom in","Ctrl +",()=>Zoom(zoom+.1)));browserMenu.Items.Add(MenuItem("Zoom out","Ctrl -",()=>Zoom(zoom-.1)));browserMenu.Items.Add(MenuItem("Reset zoom","Ctrl+0",()=>Zoom(1)));
            browserMenu.Items.Add(new ToolStripSeparator());
            settingsMenuItem=MenuItem("Settings","",()=>Add(SettingsPage));browserMenu.Items.Add(settingsMenuItem);
            browserMenu.Items.Add(MenuItem("Print page","Ctrl+P",()=>{if(active!=null&&active.view.CoreWebView2!=null)active.view.CoreWebView2.ShowPrintUI();}));
            browserMenu.Items.Add(new ToolStripSeparator());
            browserMenu.Items.Add(MenuItem("Bookmarks and history","Ctrl+H",OpenLibrary));
            browserMenu.Items.Add(MenuItem("Downloads","Ctrl+J",Downloads));
            browserMenu.Items.Add(MenuItem("Clear cookies and site data…","",ClearSiteData));
            browserMenu.Items.Add(MenuItem("About this browser","",()=>Status("RETWEAKS Browser · Microsoft Edge WebView2 "+(engineVersion==""?"(version unknown)":engineVersion))));
            browserMenu.SizeChanged+=(s,e)=>{using(var shape=Shape(browserMenu.ClientRectangle,12)){var old=browserMenu.Region;browserMenu.Region=new Region(shape);if(old!=null)old.Dispose();}};
        }
        browserMenu.BackColor=panel;browserMenu.ForeColor=fg;foreach(ToolStripItem item in browserMenu.Items)item.ForeColor=fg;
        browserMenu.Show(anchor,new Point(anchor.Width,anchor.Height+7),ToolStripDropDownDirection.BelowLeft);
    }
    static void EmitBookmarks(){var items=new List<object>();foreach(var x in shortcuts)items.Add(new{name=x.name,url=x.url});Emit(new{type="bookmarks",items=items});}
    static void Save(){EmitBookmarks();try{Directory.CreateDirectory(profile);string temp=prefs+".tmp";File.WriteAllText(temp,json.Serialize(shortcuts),Encoding.UTF8);File.Copy(temp,prefs,true);File.Delete(temp);}catch(Exception){Status("Shortcuts could not be saved.");}}
    static void Load(){
        try{if(File.Exists(prefs)){foreach(var item in json.Deserialize<List<Shortcut>>(File.ReadAllText(prefs))){if(item!=null&&Allowed(item.url)&&!String.IsNullOrWhiteSpace(item.name)&&shortcuts.Count<60)shortcuts.Add(item);}return;}}catch(Exception){}
        shortcuts.AddRange(new[]{new Shortcut{name="Google",url="https://www.google.com/"},new Shortcut{name="YouTube",url="https://www.youtube.com/"},new Shortcut{name="Discord",url="https://discord.com/app"},new Shortcut{name="GitHub",url="https://github.com/"},new Shortcut{name="Steam",url="https://store.steampowered.com/"}});
    }
    static async void UpdateHome(BrowserTab tab){
        if(tab.closed||tab.view.CoreWebView2==null||tab.url!=Home)return;
        try{await tab.view.ExecuteScriptAsync("document.body.classList.toggle('private',"+(tab.priv?"true":"false")+");document.querySelector('.shortcuts').style.display="+json.Serialize(Flag("showShortcuts")?"grid":"none")+";document.querySelector('h1').style.display="+json.Serialize(Flag("showGreeting")?"block":"none")+";document.querySelector('.logo').style.display="+json.Serialize(Flag("showLogo")?"inline":"none")+";document.querySelector('.shortcuts').style.gap="+json.Serialize(Flag("compactTiles")?"2px":"10px")+";document.body.style.fontSize="+json.Serialize(Convert.ToString(options["fontSize"])+"px")+";window.renderShortcuts && window.renderShortcuts("+json.Serialize(shortcuts)+");document.documentElement.style.setProperty('--bg','"+ColorTranslator.ToHtml(bg)+"');document.documentElement.style.setProperty('--panel','"+ColorTranslator.ToHtml(panel)+"');document.documentElement.style.setProperty('--fg','"+ColorTranslator.ToHtml(fg)+"');document.documentElement.style.setProperty('--line','"+ColorTranslator.ToHtml(line)+"');");}catch(Exception){}
    }
    static void UpdateHomes(){foreach(var t in tabs)UpdateHome(t);}
    static void Visit(string url,string title){if(String.IsNullOrWhiteSpace(title))title=new Uri(url).Host;if(history.Count>0&&Convert.ToString(history[history.Count-1]["url"])==url)history[history.Count-1]["title"]=title;else{history.Add(new Dictionary<string,object>{{"url",url},{"title",title},{"time",(long)(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds}});if(history.Count>5000)history.RemoveAt(0);}Emit(new{type="visit",url=url,title=title});UpdateLibraries();}
    static async void UpdateLibrary(BrowserTab tab){
        if(tab.closed||tab.view.CoreWebView2==null||tab.url!=Library)return;
        var recent=new List<Dictionary<string,object>>();for(int i=history.Count-1;i>=0&&recent.Count<1000;i--)recent.Add(history[i]);
        try{await tab.view.ExecuteScriptAsync("window.renderLibrary && window.renderLibrary("+json.Serialize(new{bookmarks=shortcuts,history=recent,total=history.Count})+")");}catch(Exception){}
    }
    static void UpdateLibraries(){foreach(var t in tabs)UpdateLibrary(t);}
    static void ClearHistory(){history.Clear();Emit(new{type="clear-history"});UpdateLibraries();Status("History cleared.");}
    static async void ClearSiteData(){
        if(active==null||active.view.CoreWebView2==null)return;
        if(MessageBox.Show(host,"Delete cookies, cached files and other site data for every website? You'll be signed out of websites. Bookmarks and history are kept.","Clear site data",MessageBoxButtons.OKCancel,MessageBoxIcon.Question)!=DialogResult.OK)return;
        try{await active.view.CoreWebView2.Profile.ClearBrowsingDataAsync();Status("Cookies and site data cleared.");}catch(Exception ex){Status("Site data could not be cleared: "+ex.Message);}
    }
    static void OpenLibrary(){var found=tabs.Find(t=>t.url==Library&&!t.closed);if(found!=null){Select(found);UpdateLibrary(found);}else Add(Library);}
    static void Downloads(){if(active!=null&&active.view.CoreWebView2!=null)active.view.CoreWebView2.OpenDefaultDownloadDialog();}
    static void ApplyData(Dictionary<string,object> data){
        // RETWEAKS is the source of truth for bookmarks, history, search engines and download settings.
        try{
            if(data.ContainsKey("engines")){var names=new List<string>();var map=new Dictionary<string,string>();foreach(object o in (System.Collections.IEnumerable)data["engines"]){var e=o as Dictionary<string,object>;if(e==null)continue;string name=Convert.ToString(e["name"]);string t=Convert.ToString(e["template"]);if(name.Length>0&&name.Length<60&&ValidTemplate(t)&&!map.ContainsKey(name)){names.Add(name);map[name]=t;}}if(names.Count>0){engineNames=names;templates=map;}}
            if(data.ContainsKey("customSearch"))customSearch=Convert.ToString(data["customSearch"]);
            if(data.ContainsKey("engine")){string value=Convert.ToString(data["engine"]);if(templates.ContainsKey(value))engine=value;}
            if(data.ContainsKey("bookmarks")){var icons=new Dictionary<string,string>();foreach(var x in shortcuts)if(x.icon!=null)icons[x.url]=x.icon;var list=new List<Shortcut>();foreach(object o in (System.Collections.IEnumerable)data["bookmarks"]){var b=o as Dictionary<string,object>;if(b==null)continue;string url=Convert.ToString(b["url"]);string name=Convert.ToString(b["name"]).Trim();if(Allowed(url)&&name.Length>0&&list.Count<60&&!list.Exists(x=>x.url==url)){string icon;icons.TryGetValue(url,out icon);list.Add(new Shortcut{name=name.Substring(0,Math.Min(40,name.Length)),url=url,icon=icon});}}shortcuts=list;try{Directory.CreateDirectory(profile);File.WriteAllText(prefs,json.Serialize(shortcuts),Encoding.UTF8);}catch{}}
            if(data.ContainsKey("history")){var list=new List<Dictionary<string,object>>();foreach(object o in (System.Collections.IEnumerable)data["history"]){var h=o as Dictionary<string,object>;if(h==null||!h.ContainsKey("url"))continue;string url=Convert.ToString(h["url"]);if(!Allowed(url))continue;list.Add(new Dictionary<string,object>{{"url",url},{"title",h.ContainsKey("title")?Convert.ToString(h["title"]):url},{"time",h.ContainsKey("time")?Convert.ToInt64(h["time"]):0L}});}history=list;}
            if(data.ContainsKey("downloadPrompt"))options["downloadPrompt"]=Convert.ToBoolean(data["downloadPrompt"]);
            if(data.ContainsKey("downloadFolder")){string folder=Convert.ToString(data["downloadFolder"]);if(folder.Length<2048)options["downloadFolder"]=folder;}
        }catch(Exception){}
    }
    static async void Favicon(BrowserTab tab){
        if(tab.closed||closing||tab.view.CoreWebView2==null)return;
        try{using(var stream=await tab.view.CoreWebView2.GetFaviconAsync(CoreWebView2FaviconImageFormat.Png)){
            if(tab.closed||closing)return;using(var original=Image.FromStream(stream)){
                var image=new Bitmap(original,16,16);var old=tab.title.Image;tab.title.Image=image;if(old!=null)old.Dispose();
                using(var png=new MemoryStream()){original.Save(png,System.Drawing.Imaging.ImageFormat.Png);if(png.Length>65536)return;string data="data:image/png;base64,"+Convert.ToBase64String(png.ToArray());bool changed=false;foreach(var item in shortcuts){if(new Uri(item.url).Host==new Uri(tab.url).Host&&item.icon!=data){item.icon=data;changed=true;}}if(changed){Save();UpdateHomes();}}
            }
        }}catch(Exception){}
    }
    static void Bookmark(){if(active==null||!Allowed(active.url)||active.url==Home)return;string url=active.url;var found=shortcuts.Find(s=>s.url==url);if(found!=null)shortcuts.Remove(found);else if(shortcuts.Count<60){string title=active.view.CoreWebView2.DocumentTitle;if(String.IsNullOrWhiteSpace(title))title=new Uri(url).Host;shortcuts.Add(new Shortcut{name=title.Substring(0,Math.Min(40,title.Length)),url=url});}else{Status("You have 60 shortcuts. Remove one from the home page first.");return;}Save();UpdateHomes();RefreshChrome();}
    static void RefreshChrome(){
        if(active==null)return;var core=active.view.CoreWebView2;
        if(!address.Focused)address.Text=active.url==Home?"":active.url;
        back.Enabled=core!=null&&core.CanGoBack;forward.Enabled=core!=null&&core.CanGoForward;
        reload.Text=active.busy?"×":"↻";tips.SetToolTip(reload,active.busy?"Stop loading (Esc)":"Reload (F5 / Ctrl+R)");reload.Invalidate();star.Text=shortcuts.Exists(s=>s.url==active.url)?"★":"☆";
        foreach(var t in tabs){t.chip.BackColor=t==active?panel:bg;t.title.BackColor=t.chip.BackColor;t.title.ForeColor=t==active?fg:muted;}
    }
    static void Select(BrowserTab tab){if(tab.closed)return;active=tab;foreach(var t in tabs)t.view.Visible=t==tab;tab.view.BringToFront();bool full=tab.view.CoreWebView2!=null&&tab.view.CoreWebView2.ContainsFullScreenElement;chrome.Visible=!full;status.Visible=!full;RefreshChrome();tab.view.Focus();if(newTab!=null){strip.Controls.SetChildIndex(newTab,strip.Controls.GetChildIndex(tab.chip)+1);strip.ScrollControlIntoView(newTab);}status.Visible=!full&&Flag("showStatus");}
    static void Close(BrowserTab tab){if(tab.closed)return;int index=tabs.IndexOf(tab);if(!tab.priv)closedUrls.Add(tab.url);if(closedUrls.Count>20)closedUrls.RemoveAt(0);tab.closed=true;tabs.Remove(tab);strip.Controls.Remove(tab.chip);tab.view.Dispose();if(tab.title.Image!=null)tab.title.Image.Dispose();tab.chip.Dispose();if(active==tab){active=null;if(tabs.Count>0)Select(tabs[Math.Min(index,tabs.Count-1)]);else Add(Home);} }
    static void Navigate(string text){if(active==null)return;var destination=Destination(text);if(active.view.CoreWebView2!=null)active.view.CoreWebView2.Navigate(destination);active.view.Focus();}
    static bool ShortcutKey(Keys key,Keys modifiers){
        if(key==Keys.F5){Reload((modifiers&Keys.Control)==Keys.Control);return true;}
        if(key==Keys.Escape&&active!=null&&active.busy){Reload();return true;}
        if((modifiers&Keys.Control)==Keys.Control){
            if(key==Keys.T&&(modifiers&Keys.Shift)==Keys.Shift){Reopen();return true;}
            if(key==Keys.N&&(modifiers&Keys.Shift)==Keys.Shift){Add(Home,true);return true;}
            if(key==Keys.H){OpenLibrary();return true;}
            if(key==Keys.J){Downloads();return true;}
            if(key==Keys.P&&active!=null&&active.view.CoreWebView2!=null){active.view.CoreWebView2.ShowPrintUI();return true;}
            if(key==Keys.Oemplus||key==Keys.Add){Zoom(zoom+.1);return true;}
            if(key==Keys.OemMinus||key==Keys.Subtract){Zoom(zoom-.1);return true;}
            if(key==Keys.D0){Zoom(1);return true;}
            if(key==Keys.L){address.Focus();address.SelectAll();return true;}
            if(key==Keys.T){Add(Home);return true;}
            if(key==Keys.W&&active!=null){Close(active);return true;}
            if(key==Keys.D){Bookmark();return true;}
            if(key==Keys.R){Reload((modifiers&Keys.Shift)==Keys.Shift);return true;}
            if(key==Keys.Tab&&tabs.Count>0){int delta=(modifiers&Keys.Shift)==Keys.Shift?-1:1;Select(tabs[(tabs.IndexOf(active)+delta+tabs.Count)%tabs.Count]);return true;}
        }
        if((modifiers&Keys.Alt)==Keys.Alt&&active!=null&&active.view.CoreWebView2!=null){if(key==Keys.Left&&active.view.CanGoBack){active.view.GoBack();return true;}if(key==Keys.Right&&active.view.CanGoForward){active.view.GoForward();return true;}if(key==Keys.Home){Navigate(Home);return true;}}
        return false;
    }
    static async Task<BrowserTab> Add(string url){return await Add(url,false);}
    static async Task<BrowserTab> Add(string url,bool priv){
        if(closing||environment==null)return null;if(tabs.Count>=20){Status("Close a tab before opening another (20 tabs maximum).");return null;}
        var tab=new BrowserTab();tab.priv=priv;tab.chip=new RoundPanel{Width=190,Height=34,Margin=new Padding(3,3,3,0),BackColor=panel};
        tab.title=Button(priv?"Private · New tab":"New tab",150,tab.chip,()=>Select(tab));tab.title.TextAlign=ContentAlignment.MiddleLeft;tab.title.AutoEllipsis=true;tab.title.ImageAlign=ContentAlignment.MiddleLeft;tab.title.TextImageRelation=TextImageRelation.ImageBeforeText;tab.title.Location=new Point(9,0);
        var close=Button("×",27,tab.chip,()=>Close(tab));close.Location=new Point(158,0);
        strip.Controls.Add(tab.chip);tab.view=new WebView2{Dock=DockStyle.Fill,DefaultBackgroundColor=bg,ZoomFactor=zoom};deck.Controls.Add(tab.view);tabs.Add(tab);Select(tab);
        try{
            if(priv){var controllerOptions=environment.CreateCoreWebView2ControllerOptions();controllerOptions.IsInPrivateModeEnabled=true;await tab.view.EnsureCoreWebView2Async(environment,controllerOptions);}
            else await tab.view.EnsureCoreWebView2Async(environment);if(tab.closed||closing)return null;
            var core=tab.view.CoreWebView2;core.Settings.AreHostObjectsAllowed=false;core.IsMuted=Flag("muteNewTabs");core.Settings.AreDevToolsEnabled=true;core.Settings.IsWebMessageEnabled=true;
            core.SetVirtualHostNameToFolderMapping(Host,AssetsPath(),CoreWebView2HostResourceAccessKind.DenyCors);
            core.PermissionRequested+=(s,e)=>{if(Convert.ToString(options["permissions"])=="Block")e.State=CoreWebView2PermissionState.Deny;};
            core.NewWindowRequested+=async (s,e)=>{e.Handled=true;if(!Flag("popups")){Status("Popup blocked. Change this in Settings > Site settings.");return;}if(!Allowed(e.Uri)&&e.Uri!="about:blank")return;var deferral=e.GetDeferral();try{var created=await Add(Home,tab.priv);if(created!=null&&!created.closed)e.NewWindow=created.view.CoreWebView2;}catch(Exception){if(!closing)Status("The new tab could not be opened.");}finally{try{deferral.Complete();}catch{}}};
            core.NavigationStarting+=(s,e)=>{if(tab.closed||closing)return;if(!Allowed(e.Uri)&&e.Uri!="about:blank"){e.Cancel=true;Status("This browser opens web addresses only.");return;}core.Settings.IsScriptEnabled=Trusted(e.Uri)||Flag("scripts");tab.navigation=e.NavigationId;tab.busy=true;if(active==tab){Status("Loading…");RefreshChrome();}};
            core.SourceChanged+=(s,e)=>{if(tab.closed||closing)return;tab.url=core.Source;if(active==tab)RefreshChrome();};
            core.HistoryChanged+=(s,e)=>{if(tab.closed||closing)return;if(active==tab)RefreshChrome();};
            core.DocumentTitleChanged+=(s,e)=>{if(tab.closed||closing)return;tab.title.Text=(tab.priv?"Private · ":"")+(tab.url==Home?"New tab":core.DocumentTitle);if(!tab.priv&&Allowed(tab.url)&&!Trusted(tab.url))Emit(new{type="title",url=tab.url,title=core.DocumentTitle});};
            core.NavigationCompleted+=(s,e)=>{if(tab.closed||closing||e.NavigationId!=tab.navigation)return;tab.busy=false;if(e.IsSuccess&&!tab.priv&&Allowed(tab.url)&&!Trusted(tab.url))Visit(tab.url,core.DocumentTitle);if(active==tab){RefreshChrome();Status(e.IsSuccess||e.WebErrorStatus==CoreWebView2WebErrorStatus.OperationCanceled?"":("Page could not load: "+e.WebErrorStatus+". Check the address or reload."));}UpdateHome(tab);UpdateSettings(tab);UpdateLibrary(tab);};
            core.FaviconChanged+=(s,e)=>Favicon(tab);
            core.WebMessageReceived+=(s,e)=>{
                if(tab.closed||closing)return;
                if(!Trusted(e.Source))return;
                try{var data=json.Deserialize<Dictionary<string,object>>(e.WebMessageAsJson);string op=Convert.ToString(data["op"]);string target=data.ContainsKey("url")?Convert.ToString(data["url"]):"";
                    if(op=="save-settings"&&e.Source==SettingsPage){bool oldPrompt=Flag("downloadPrompt");string oldFolder=Convert.ToString(options["downloadFolder"]);if(data.ContainsKey("customSearch")){string custom=Convert.ToString(data["customSearch"]).Trim();if(custom==""||ValidTemplate(custom)){if(custom!=customSearch){customSearch=custom;Emit(new{type="setting",key="browser_custom_search",value=customSearch});}if(custom!=""){templates["Custom"]=custom;if(!engineNames.Contains("Custom"))engineNames.Add("Custom");}}else Status("Custom search must be an https:// address with {q} where the search words go.");}SetEngine(Convert.ToString(data["engine"]));zoom=Math.Max(.5,Math.Min(2,Convert.ToDouble(data["zoom"])));ReadOptions((Dictionary<string,object>)data["options"]);SaveSettings();ApplyOptions();UpdateSettings(tab);if(Flag("downloadPrompt")!=oldPrompt)Emit(new{type="setting",key="browser_ask_download",value=Flag("downloadPrompt")});if(Convert.ToString(options["downloadFolder"])!=oldFolder)Emit(new{type="setting",key="browser_download_dir",value=Convert.ToString(options["downloadFolder"])});}
                    else if(op=="open"&&e.Source==Library&&Allowed(target)){Navigate(target);}
                    else if(op=="open-tab"&&e.Source==Library&&Allowed(target)){Add(target);}
                    else if(op=="rename-shortcut"&&e.Source==Library){string name=Convert.ToString(data["name"]).Trim();var found=shortcuts.Find(x=>x.url==target);if(found!=null&&name.Length>0){found.name=name.Substring(0,Math.Min(40,name.Length));Save();UpdateHomes();UpdateLibraries();}}
                    else if(op=="clear-history"&&e.Source==Library){ClearHistory();}
                    else if(op=="clear-site-data"&&(e.Source==Library||e.Source==SettingsPage)){ClearSiteData();}
                    else if(op=="reset-settings"&&e.Source==SettingsPage){options=Defaults();SetEngine(engineNames.Count>0?engineNames[0]:"Google");zoom=1;SaveSettings();ApplyOptions();UpdateSettings(tab);Emit(new{type="setting",key="browser_ask_download",value=Flag("downloadPrompt")});Emit(new{type="setting",key="browser_download_dir",value=""});}
                    else if(op=="navigate"){if(active==tab)Navigate(target);}
                    else if(op=="add-shortcut"&&Allowed(target)&&shortcuts.Count<60){string name=Convert.ToString(data["name"]).Trim();if(name.Length>0&&!shortcuts.Exists(x=>x.url==target)){shortcuts.Add(new Shortcut{name=name.Substring(0,Math.Min(40,name.Length)),url=target});Save();UpdateHomes();}}
                    else if(op=="remove-shortcut"){shortcuts.RemoveAll(x=>x.url==target);Save();UpdateHomes();UpdateLibraries();}
                }catch(Exception){Status("That shortcut could not be saved.");}
            };
            core.DownloadStarting+=(s,e)=>{
                if(!Flag("downloadPrompt")){string folder=Convert.ToString(options["downloadFolder"]);if(folder==""){Status("Downloading "+Path.GetFileName(e.ResultFilePath)+"… (Downloads button shows progress)");return;}if(Directory.Exists(folder)){string name=Path.GetFileName(e.ResultFilePath);string path=Path.Combine(folder,name);int suffix=1;while(File.Exists(path))path=Path.Combine(folder,Path.GetFileNameWithoutExtension(name)+" ("+(suffix++)+")"+Path.GetExtension(name));e.ResultFilePath=path;return;}}
                e.Handled=true;var deferral=e.GetDeferral();try{using(var dialog=new SaveFileDialog{FileName=Path.GetFileName(e.ResultFilePath),InitialDirectory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads"),OverwritePrompt=true}){
                    if(dialog.ShowDialog(host)!=DialogResult.OK){e.Cancel=true;return;}e.ResultFilePath=dialog.FileName;Status("Downloading "+Path.GetFileName(dialog.FileName)+"…");var download=e.DownloadOperation;download.StateChanged+=(sender,args)=>{if(!closing)Status(download.State==CoreWebView2DownloadState.Completed?"Download complete.":download.State==CoreWebView2DownloadState.Interrupted?"Download interrupted. Try again from the page.":"Downloading…");};
                }}finally{deferral.Complete();}
            };
            core.ProcessFailed+=(s,e)=>{if(closing||tab.closed)return;if(e.ProcessFailedKind==CoreWebView2ProcessFailedKind.BrowserProcessExited){Emit(new{type="stopped",message="Browser stopped. Recovering…"});closing=true;host.Close();loop.ExitThread();}else if(active==tab)Status("This page stopped. Reload it, or close and reopen the tab.");};
            core.ContainsFullScreenElementChanged+=(s,e)=>{if(active==tab){chrome.Visible=!core.ContainsFullScreenElement;status.Visible=!core.ContainsFullScreenElement;}};
            tab.view.KeyDown+=(s,e)=>{if(ShortcutKey(e.KeyCode,e.Modifiers)){e.Handled=true;e.SuppressKeyPress=true;}};
            ApplyTheme();ApplyOptions();core.Navigate(Allowed(url)?url:Home);return tab;
        }catch(Exception ex){if(!tab.closed){tab.title.Text="Unavailable";Status("Browser unavailable: "+ex.Message);Emit(new{type="error",message="Browser could not initialize. Check Microsoft Edge WebView2 Runtime."});}return null;}
    }
    static void ApplyTheme(){
        host.BackColor=bg;deck.BackColor=bg;chrome.BackColor=bg;strip.BackColor=bg;bar.BackColor=bg;addressBox.BackColor=panel;addressBox.edge=line;address.BackColor=panel;address.ForeColor=fg;status.BackColor=bg;status.ForeColor=muted;
        Action<Control> color=null;color=c=>{foreach(Control child in c.Controls){if(child is Button){child.BackColor=panel;child.ForeColor=fg;((Button)child).FlatAppearance.MouseOverBackColor=line;}if(!(child is WebView2))color(child);}};color(chrome);
        foreach(var t in tabs){t.view.DefaultBackgroundColor=bg;if(t.view.CoreWebView2!=null)t.view.CoreWebView2.Profile.PreferredColorScheme=Convert.ToString(options["theme"])=="Light"?CoreWebView2PreferredColorScheme.Light:Convert.ToString(options["theme"])=="System"?CoreWebView2PreferredColorScheme.Auto:CoreWebView2PreferredColorScheme.Dark;}
        UpdateHomes();RefreshChrome();addressBox.Invalidate();
    }
    static void Colors(Dictionary<string,object> data){bg=ColorTranslator.FromHtml(Convert.ToString(data["BG"]));panel=ColorTranslator.FromHtml(Convert.ToString(data["PANEL"]));fg=ColorTranslator.FromHtml(Convert.ToString(data["FG"]));muted=ColorTranslator.FromHtml(Convert.ToString(data["MUTED"]));line=ColorTranslator.FromHtml(Convert.ToString(data["LINE"]));}
    static void Build(){
        chrome=new Panel{Dock=DockStyle.Top,Height=92,Padding=new Padding(8,2,8,5)};
        var tabrow=new Panel{Dock=DockStyle.Top,Height=39};strip=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=false,AutoScroll=true};tabrow.Controls.Add(strip);newTab=Button("+",34,strip,()=>{Add(Home);});newTab.Margin=new Padding(4,3,4,0);
        bar=new Panel{Dock=DockStyle.Bottom,Height=45};
        var nav=new FlowLayoutPanel{Dock=DockStyle.Left,Width=166,WrapContents=false,Padding=new Padding(0,4,0,0)};
        back=Button("←",34,nav,()=>{if(active!=null&&active.view.CanGoBack)active.view.GoBack();});forward=Button("→",34,nav,()=>{if(active!=null&&active.view.CanGoForward)active.view.GoForward();});reload=Button("↻",34,nav,()=>Reload());Button("⌂",34,nav,()=>Navigate(Allowed(Convert.ToString(options["homeUrl"]))?Convert.ToString(options["homeUrl"]):Home));
        var actions=new FlowLayoutPanel{Dock=DockStyle.Right,Width=126,WrapContents=false,Padding=new Padding(0,4,0,0)};star=Button("☆",34,actions,Bookmark);Button("↓",34,actions,()=>{if(active!=null&&active.view.CoreWebView2!=null)active.view.CoreWebView2.OpenDefaultDownloadDialog();});Button settings=null;settings=Button("•••",34,actions,()=>Menu(settings));settings.AccessibleName="Browser settings and tools";tips.SetToolTip(settings,"Browser settings and tools");
        addressBox=new RoundPanel{Dock=DockStyle.Fill,Padding=new Padding(17,10,15,6),Margin=new Padding(4)};
        address=new TextBox{Dock=DockStyle.Fill,BorderStyle=BorderStyle.None,Font=new Font("Segoe UI",11),ShortcutsEnabled=true,MaxLength=8192,AccessibleName="Address and search"};addressBox.Controls.Add(address);SendMessage(address.Handle,0x1501,IntPtr.Zero,"Search the web or enter an address");address.KeyDown+=(s,e)=>{if(e.KeyCode==Keys.Enter){Navigate(address.Text);e.SuppressKeyPress=true;}};
        bar.Controls.Add(addressBox);bar.Controls.Add(actions);bar.Controls.Add(nav);chrome.Controls.Add(tabrow);chrome.Controls.Add(bar);
        status=new Label{Dock=DockStyle.Bottom,Height=22,Padding=new Padding(14,3,0,0),Font=new Font("Segoe UI",8)};
        deck=new Panel{Dock=DockStyle.Fill};host.Controls.Add(deck);host.Controls.Add(status);host.Controls.Add(chrome);host.KeyPreview=true;host.KeyDown+=(s,e)=>{if(ShortcutKey(e.KeyCode,e.Modifiers)){e.Handled=true;e.SuppressKeyPress=true;}};
    }
    static async void Initialize(){try{environment=await CoreWebView2Environment.CreateAsync(null,profile);await Add(!testing&&Allowed(Convert.ToString(options["startupUrl"]))?Convert.ToString(options["startupUrl"]):Home);Emit(new{type="ready",embedded=true});Emit(new{type="loaded",message="RETWEAKS Browser ready."});}catch(Exception ex){Status("Browser could not start: "+ex.Message);Emit(new{type="error",message="Browser unavailable. Install Microsoft Edge WebView2 Runtime and retry."});}}
    static async void Command(string raw){try{var data=json.Deserialize<Dictionary<string,object>>(raw);string op=Convert.ToString(data["op"]);
        if(op=="close"){closing=true;host.Close();loop.ExitThread();}
        else if(op=="visibility"){visible=Convert.ToBoolean(data["visible"]);Sync();}
        else if(op=="theme"){Colors(data);if(data.ContainsKey("data"))ApplyData((Dictionary<string,object>)data["data"]);ApplyTheme();}
        else if(op=="data"){ApplyData(data);UpdateHomes();UpdateLibraries();foreach(var t in tabs)UpdateSettings(t);RefreshChrome();}
        else if(op=="navigate"){Navigate(Convert.ToString(data["url"]));}
        else if(op=="new-tab"){Add(Home,data.ContainsKey("private")&&Convert.ToBoolean(data["private"]));}
        else if(op=="inspect"){string document=active!=null&&active.view.CoreWebView2!=null?await active.view.ExecuteScriptAsync("JSON.stringify({title:document.title,settings:document.querySelectorAll('[data-option]').length,message:document.querySelector('#message')?.textContent,shortcuts:document.querySelectorAll('.tile').length,icons:Array.from(document.querySelectorAll('.tile .icon img')).filter(i=>i.complete&&i.naturalWidth>0).length})"):"null";Emit(new{type="state",history=history.Count,bookmarks=shortcuts.Count,privateTabs=tabs.FindAll(t=>t.priv).Count,engines=engineNames,newTabAfterActive=active!=null&&strip.Controls.GetChildIndex(newTab)==strip.Controls.GetChildIndex(active.chip)+1,engine=engine,zoom=zoom,options=options,tabs=tabs.Count,url=active==null?"":active.url,embedded=IsChild(parent,host.Handle),visible=host.Visible,width=host.Width,height=host.Height,document=document,canBack=active!=null&&active.view.CanGoBack,canForward=active!=null&&active.view.CanGoForward});}
        else if(testing&&op=="test-settings"){Menu(newTab);browserMenu.Close(ToolStripDropDownCloseReason.ItemClicked);settingsMenuItem.PerformClick();Emit(new{type="test-done"});}
        else if(testing&&op=="test-save-settings"&&active.url==SettingsPage){await active.view.ExecuteScriptAsync("document.querySelector('#engine').value='Bing';document.querySelector('#zoom').value='1.25';document.querySelector('#showHome').checked=false;document.querySelector('#permissions').value='Block';document.querySelector('#save').click()");}
        else if(testing&&op=="test-reset-settings"&&active.url==SettingsPage){await active.view.ExecuteScriptAsync("window.chrome.webview.postMessage({op:'reset-settings'})");}
        else if(testing&&op=="test-reload"){Reload();Emit(new{type="test-done"});}
        else if(testing&&op=="test-new-tab"){await Add(Home);Emit(new{type="test-done"});}
        else if(testing&&op=="test-close-tab"&&active!=null){Close(active);Emit(new{type="test-done"});}
        else if(testing&&op=="test-tab-race"){var pending=Add(Home);if(active!=null)Close(active);await pending;Emit(new{type="test-done"});}
        else if(testing&&op=="test-back"&&active!=null&&active.view.CanGoBack)active.view.GoBack();
        else if(testing&&op=="test-forward"&&active!=null&&active.view.CanGoForward)active.view.GoForward();
        else if(testing&&op=="test-bookmark")Bookmark();
        else if(testing&&op=="test-shortcut"&&active!=null&&active.url==Home){await active.view.ExecuteScriptAsync("window.chrome.webview.postMessage({op:'add-shortcut',name:'Local test shortcut',url:'https://example.invalid/retweaks-test'})");}
        else if(testing&&op=="test-remove-shortcut"&&active!=null&&active.url==Home){await active.view.ExecuteScriptAsync("window.chrome.webview.postMessage({op:'remove-shortcut',url:'https://example.invalid/retweaks-test'})");}
        else if(testing&&op=="test-popup"&&active!=null&&active.view.CoreWebView2!=null){Uri target;string url=Convert.ToString(data["url"]);if(Uri.TryCreate(url,UriKind.Absolute,out target)&&target.IsLoopback&&target.Scheme=="http")await active.view.ExecuteScriptAsync("window.open("+json.Serialize(url)+",'_blank')");}
        else if(testing&&op=="test-destination")Emit(new{type="destination",url=Destination(Convert.ToString(data["text"]))});
        else if(testing&&op=="test-navigate"){Uri uri;string url=Convert.ToString(data["url"]);if(Uri.TryCreate(url,UriKind.Absolute,out uri)&&uri.IsLoopback&&uri.Scheme=="http")Navigate(url);}
    }catch(Exception ex){Status("Browser action failed: "+ex.Message);}}
    [STAThread]static void Main(string[] args){
        Console.SetIn(new StreamReader(Console.OpenStandardInput(),new UTF8Encoding(false)));Console.SetOut(new StreamWriter(Console.OpenStandardOutput(),new UTF8Encoding(false)){AutoFlush=true});
        try{parent=new IntPtr(long.Parse(args[0]));if(!IsWindow(parent))return;testing=Array.IndexOf(args,"--offline-test")>=0;
            profile=testing?args[2]:Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RETWEAKS","Browser");prefs=Path.Combine(profile,"shortcuts.json");Load();LoadSettings();
            try{SetThreadDpiAwarenessContext(GetWindowDpiAwarenessContext(parent));}catch(EntryPointNotFoundException){}
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            // An error inside a click or page event is reported in the status line instead of ending the browser.
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);Application.ThreadException+=(s,e)=>{try{if(status!=null&&!closing)Status("Browser action failed: "+e.Exception.Message);}catch{}};
            try{engineVersion=CoreWebView2Environment.GetAvailableBrowserVersionString();}catch{}host=new Form{TopLevel=false,FormBorderStyle=FormBorderStyle.None,ShowInTaskbar=false};
            var first=json.Deserialize<Dictionary<string,object>>(Console.ReadLine());Colors(first);if(first.ContainsKey("data"))ApplyData((Dictionary<string,object>)first["data"]);Build();ApplyTheme();SetParent(host.Handle,parent);loop=new ApplicationContext();host.FormClosed+=(s,e)=>loop.ExitThread();Sync();host.BeginInvoke((Action)Initialize);
            var timer=new System.Windows.Forms.Timer{Interval=100};timer.Tick+=(s,e)=>{if(!IsWindow(parent)){host.Close();loop.ExitThread();}else Sync();};timer.Start();
            var reader=new Thread(()=>{try{string raw;while((raw=Console.ReadLine())!=null){string copy=raw;host.BeginInvoke((Action)(()=>Command(copy)));}host.BeginInvoke((Action)(()=>host.Close()));}catch{}});reader.IsBackground=true;reader.Start();
            Application.Run(loop);closing=true;timer.Dispose();foreach(var tab in tabs){tab.closed=true;tab.view.Dispose();}if(browserMenu!=null)browserMenu.Dispose();host.Dispose();
        }catch(Exception ex){Emit(new{type="error",message="RETWEAKS Browser could not start: "+ex.Message});}
    }
}
