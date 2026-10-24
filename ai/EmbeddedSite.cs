using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

class EmbeddedSite {
    static string SiteTitle="PC Builds bottleneck calculator";
    static string Url="https://pc-builds.com/bottleneck-calculator/";
    [DllImport("user32.dll")] static extern IntPtr SetParent(IntPtr child,IntPtr parent);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr window);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] static extern bool IsChild(IntPtr parent,IntPtr child);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr window,out Rect rect);
    [DllImport("user32.dll")] static extern IntPtr GetWindowDpiAwarenessContext(IntPtr window);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    struct Rect {public int left,top,right,bottom;}
    static JavaScriptSerializer json=new JavaScriptSerializer();
    static Form host;
    static WebView2 view;
    static IntPtr parent;
    static ApplicationContext loop;
    static bool pageVisible=true,offline,direct,ready,remoteTest,loaded,closing;
    static int attempts,navigations;
    static ulong navigationId;
    static string currentUrl;
    static DateTime navigationStarted;
    static System.Windows.Forms.Timer retryTimer;
    static string profile;
    static int siteStatus;
    static void Emit(object data) {Console.WriteLine(json.Serialize(data));Console.Out.Flush();}
    static void Sync() {
        bool visible=pageVisible && IsWindowVisible(parent);
        host.Enabled=visible;
        if(visible && !host.Visible)host.Show();
        if(!visible && host.Visible)host.Hide();
        Rect r;GetClientRect(parent,out r);
        if(host.Width!=r.right || host.Height!=r.bottom)host.SetBounds(0,0,Math.Max(1,r.right),Math.Max(1,r.bottom));
    }
    static void FramePage() {
        direct=false;siteStatus=0;
        string source=offline ? "srcdoc=\"<!doctype html><title>Local calculator test</title><h1>Calculator iframe ready</h1>\"" : "src=\""+Url+"\"";
        view.NavigateToString("<!doctype html><html><head><meta name=viewport content='width=device-width, initial-scale=1'><style>html,body{margin:0;width:100%;height:100%;background:#101214;overflow:hidden}iframe{width:100%;height:100%;border:0;display:block}</style></head><body><iframe name='calculator' title='"+SiteTitle+"' "+source+" allow='fullscreen'></iframe></body></html>");
    }
    static void Status(string type,string message) {Emit(new {type=type,message=message});}
    static void CancelRetry() {if(retryTimer!=null){retryTimer.Stop();retryTimer.Dispose();retryTimer=null;}}
    static void OpenSite(bool reset) {
        CancelRetry();
        if(reset)attempts=0;
        loaded=false;
        if(offline && !remoteTest) {FramePage();return;}
        direct=true;siteStatus=0;
        view.CoreWebView2.Navigate(currentUrl ?? Url);
    }
    static void Retry(string reason) {
        if(closing || retryTimer!=null)return;
        if(attempts>=3) {loaded=true;Status("error","The website is still unavailable after automatic retries. Check your connection or return to this tab later.");return;}
        attempts++;
        Status("retrying",reason+" Retrying automatically ("+attempts+"/3)...");
        retryTimer=new System.Windows.Forms.Timer {Interval=remoteTest?150:(int)Math.Pow(2,attempts-1)*1000};
        retryTimer.Tick+=(s,e)=> {CancelRetry();if(!closing)OpenSite(false);};retryTimer.Start();
    }
    static async void Initialize() {
        for(int attempt=0;attempt<3 && !closing;attempt++) {
            try {
                var environment=await CoreWebView2Environment.CreateAsync(null,profile);
                await view.EnsureCoreWebView2Async(environment);
                view.CoreWebView2.Settings.AreHostObjectsAllowed=false;
                view.CoreWebView2.Settings.IsWebMessageEnabled=false;
                view.CoreWebView2.NewWindowRequested+=(s,e)=> {e.Handled=true;if(e.Uri.StartsWith("https://",StringComparison.OrdinalIgnoreCase))view.CoreWebView2.Navigate(e.Uri);};
                view.CoreWebView2.NavigationStarting+=(s,e)=> {
                    navigationId=e.NavigationId;navigationStarted=DateTime.UtcNow;loaded=false;siteStatus=0;navigations++;
                    if(e.Uri.StartsWith("https://",StringComparison.OrdinalIgnoreCase) || (remoteTest && new Uri(e.Uri).IsLoopback))currentUrl=e.Uri;
                    Status("loading","Loading "+SiteTitle+"...");
                };
                view.CoreWebView2.NavigationCompleted+=async (s,e)=> {
                    if(e.NavigationId!=navigationId || closing)return;
                    siteStatus=e.HttpStatusCode;
                    if(!direct) {loaded=true;Status("loaded","Local browser test ready.");return;}
                    if(siteStatus==401 || siteStatus==403 || siteStatus==429) {
                        CancelRetry();loaded=true;
                        Status("notice",siteStatus==429?"The website is rate-limiting requests. Please wait before trying again.":"Complete any sign-in or browser check displayed by the website.");return;
                    }
                    if(e.WebErrorStatus==CoreWebView2WebErrorStatus.OperationCanceled)return;
                    if(!e.IsSuccess || siteStatus>=400) {Retry(siteStatus>=400?"Website returned HTTP "+siteStatus+".":"The connection was interrupted ("+e.WebErrorStatus+").");return;}
                    if(!remoteTest)await System.Threading.Tasks.Task.Delay(800);
                    if(e.NavigationId!=navigationId || closing)return;
                    string missing="false";
                    try {missing=await view.ExecuteScriptAsync("JSON.stringify(/^(404|.*page not found.*|.*404.*)$/i.test(document.title.trim()) || Array.from(document.querySelectorAll('h1')).some(h=>/^(404|page not found)$/i.test(h.textContent.trim())))");} catch(Exception) {if(!closing)Retry("The page changed while loading.");return;}
                    if(e.NavigationId!=navigationId || closing)return;
                    if(missing=="\"true\"") {Retry("The website did not finish opening the requested page.");return;}
                    CancelRetry();attempts=0;loaded=true;Status("loaded",SiteTitle+" ready.");
                };
                view.CoreWebView2.ProcessFailed+=(s,e)=> {
                    if(closing)return;
                    if(e.ProcessFailedKind==CoreWebView2ProcessFailedKind.BrowserProcessExited) {
                        Status("stopped","The browser stopped. Recovering automatically...");closing=true;CancelRetry();host.Close();loop.ExitThread();
                    } else Retry("The page renderer stopped.");
                };
                ready=true;currentUrl=Url;OpenSite(true);Emit(new {type="ready",embedded=true});return;
            } catch(Exception) {
                if(attempt<2) Status("retrying","Starting the embedded browser again...");
                else Status("error","Embedded browser unavailable. Check that Microsoft Edge WebView2 Runtime is installed.");
            }
            if(attempt<2 && !closing)await System.Threading.Tasks.Task.Delay(750*(attempt+1));
        }
    }
    static async void Command(string line) {
        try {
            var data=json.Deserialize<Dictionary<string,object>>(line);string op=Convert.ToString(data["op"]);
            if(op=="close"){closing=true;CancelRetry();host.Close();loop.ExitThread();}
            else if(op=="visibility"){pageVisible=Convert.ToBoolean(data["visible"]);Sync();}
            else if(op=="reload" && ready)OpenSite(true);
            else if(op=="direct" && ready)OpenSite(true);
            else if(op=="theme"){host.BackColor=ColorTranslator.FromHtml(Convert.ToString(data["BG"]));view.DefaultBackgroundColor=host.BackColor;}
            else if(op=="test-navigate" && offline && remoteTest && ready) {
                Uri target;
                if(Uri.TryCreate(Convert.ToString(data["url"]),UriKind.Absolute,out target) && target.IsLoopback && target.Scheme=="http") {currentUrl=target.AbsoluteUri;OpenSite(true);}
            }
            else if(op=="inspect" && ready) {
                string state=await view.ExecuteScriptAsync("JSON.stringify({iframe:!!document.querySelector('iframe[name=calculator]'),src:document.querySelector('iframe')?.getAttribute('src'),title:document.title})");
                Emit(new {type="state",embedded=IsChild(parent,host.Handle),visible=host.Visible,enabled=host.Enabled,width=host.Width,height=host.Height,document=state,url=Url,direct=direct,httpStatus=siteStatus,loaded=loaded,attempts=attempts,navigations=navigations});
            }
        } catch(Exception) {Emit(new {type="error",message="The browser action could not be completed. Switch tabs and reopen this tab to retry."});}
    }
    [STAThread] static void Main(string[] args) {
        Console.SetIn(new StreamReader(Console.OpenStandardInput(),new UTF8Encoding(false)));
        Console.SetOut(new StreamWriter(Console.OpenStandardOutput(),new UTF8Encoding(false)){AutoFlush=true});
        try {
            parent=new IntPtr(long.Parse(args[0]));offline=Array.IndexOf(args,"--offline-test")>=0;
            profile=offline?args[2]:Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RETWEAKS","BottleneckBrowser");
            if(!IsWindow(parent))return;
            try{SetThreadDpiAwarenessContext(GetWindowDpiAwarenessContext(parent));}catch(EntryPointNotFoundException){}
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            host=new Form {TopLevel=false,FormBorderStyle=FormBorderStyle.None,ShowInTaskbar=false,MinimumSize=Size.Empty};
            view=new WebView2 {Dock=DockStyle.Fill};host.Controls.Add(view);
            host.KeyPreview=true;
            KeyEventHandler globalSearch=(s,e)=>{if(e.Control&&e.KeyCode==Keys.K){e.Handled=true;e.SuppressKeyPress=true;Emit(new{type="global-search"});}};
            host.KeyDown+=globalSearch;view.KeyDown+=globalSearch;
            var initial=json.Deserialize<Dictionary<string,object>>(Console.ReadLine());
            if(initial.ContainsKey("builder") && Convert.ToBoolean(initial["builder"])) {
                Url="https://www.buildcores.com/new-build";SiteTitle="BuildCores 3D PC Builder";
                if(!offline)profile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RETWEAKS","BuildCoresBrowser");
            }
            if(initial.ContainsKey("activation") && Convert.ToBoolean(initial["activation"])) {
                Url="https://massgrave.dev/";SiteTitle="Windows Activation";
                if(!offline)profile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RETWEAKS","ActivationBrowser");
            }
            if(initial.ContainsKey("windhawk") && Convert.ToBoolean(initial["windhawk"])) {
                Url="https://windhawk.net/mods";SiteTitle="Windhawk";
                if(!offline)profile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RETWEAKS","WindhawkBrowser");
            }
            if(offline && initial.ContainsKey("test_url")) {
                Uri test;
                if(Uri.TryCreate(Convert.ToString(initial["test_url"]),UriKind.Absolute,out test) && test.IsLoopback && test.Scheme=="http") {Url=test.AbsoluteUri;remoteTest=true;}
            }
            host.BackColor=ColorTranslator.FromHtml(Convert.ToString(initial["BG"]));view.DefaultBackgroundColor=host.BackColor;
            SetParent(host.Handle,parent);loop=new ApplicationContext();host.FormClosed+=(s,e)=>loop.ExitThread();
            Sync();host.BeginInvoke((Action)Initialize);
            var timer=new System.Windows.Forms.Timer {Interval=100};
            timer.Tick+=(s,e)=>{if(!IsWindow(parent)){host.Close();loop.ExitThread();}else {
                Sync();
                if(ready && direct && !loaded && retryTimer==null && (DateTime.UtcNow-navigationStarted).TotalSeconds>35) {
                    view.CoreWebView2.Stop();Retry("The website took too long to respond.");
                }
            }};timer.Start();
            var reader=new Thread(()=> {try {string line;while((line=Console.ReadLine())!=null){string copy=line;host.BeginInvoke((Action)(()=>Command(copy)));}host.BeginInvoke((Action)(()=>{host.Close();loop.ExitThread();}));}catch{}});
            reader.IsBackground=true;reader.Start();Application.Run(loop);closing=true;CancelRetry();timer.Dispose();view.Dispose();host.Dispose();
        }catch(Exception){Emit(new {type="error",message="The embedded browser could not start. Switch tabs and reopen this tab to retry."});}
    }
}
