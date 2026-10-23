using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Security.Cryptography;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

class GeminiChat : Form
{
    readonly TextBox key = new TextBox { UseSystemPasswordChar = true, Dock = DockStyle.Fill };
    readonly ComboBox model = new ComboBox { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDown };
    readonly RichTextBox chat = new RichTextBox { Dock = DockStyle.Fill, ReadOnly = true, BackColor = Color.FromArgb(24,28,36), ForeColor = Color.WhiteSmoke, BorderStyle = BorderStyle.None, Font = new Font("Segoe UI", 11) };
    readonly TextBox input = new TextBox { Multiline = true, Dock = DockStyle.Fill, Font = new Font("Segoe UI", 11), ScrollBars = ScrollBars.Vertical };
    readonly Button send = new Button { Text = "Send", Dock = DockStyle.Fill };
    readonly Button refresh = new Button { Text = "Load models", Dock = DockStyle.Fill };
    readonly Button clear = new Button { Text = "New chat", Dock = DockStyle.Fill };
    readonly Label status = new Label { Text = "Your key is loaded automatically. Replacement keys are remembered on this Windows account.", Dock = DockStyle.Fill, AutoSize = true };
    readonly List<object> history = new List<object>();
    readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 16000000 };
    readonly HttpClient http = new HttpClient { Timeout = TimeSpan.FromMinutes(2) };
    bool busy;
    const string BundledKey = "AQ.Ab8RN6LKgDQcx-o016PLwjinorKrRq4HE5OJ0cVZfRvTDo4hhg";
    static readonly string KeyFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "GeminiChat", "key-v2.dat");
    static string ReadKey() {
        try { if (File.Exists(KeyFile)) return Encoding.UTF8.GetString(ProtectedData.Unprotect(File.ReadAllBytes(KeyFile), null, DataProtectionScope.CurrentUser)); } catch { }
        return BundledKey;
    }
    void SaveKey() {
        Directory.CreateDirectory(Path.GetDirectoryName(KeyFile));
        File.WriteAllBytes(KeyFile, ProtectedData.Protect(Encoding.UTF8.GetBytes(ApiKey()), null, DataProtectionScope.CurrentUser));
    }

    public GeminiChat()
    {
        key.Text = BundledKey;
        AutoScaleMode = AutoScaleMode.None; Text = "Gemini Chat"; Width = 980; Height = 780; MinimumSize = new Size(680, 540);
        BackColor = Color.FromArgb(19,15,32); ForeColor = Color.FromArgb(238,233,255);
        Font = new Font("Segoe UI", 11); StartPosition = FormStartPosition.CenterScreen;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(30,22,30,18), ColumnCount = 1, RowCount = 5 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,64));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,116));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,36));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,28));
        var header = new Panel { Dock = DockStyle.Fill };
        header.Controls.Add(new Label { Text = "Gemini", Font = new Font("Segoe UI",22,FontStyle.Bold), AutoSize = true, Location = new Point(0,0) });
        clear.Dock = DockStyle.Right; clear.Width = 115; clear.Height = 38;
        clear.FlatStyle = FlatStyle.Flat; clear.FlatAppearance.BorderColor = Color.FromArgb(75,62,109);
        clear.BackColor = Color.FromArgb(32,26,47); clear.ForeColor = ForeColor;
        header.Controls.Add(clear); layout.Controls.Add(header,0,0);
        chat.BackColor = BackColor; chat.Font = new Font("Segoe UI",12); chat.DetectUrls = true;
        chat.Margin = new Padding(10,12,10,22); layout.Controls.Add(chat,0,1);
        var composer = new RoundedPanel { Dock = DockStyle.Fill, Padding = new Padding(26,25,18,22), Margin = new Padding(0,6,0,6), BackColor = Color.FromArgb(33,28,46) };
        var composeLayout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, BackColor = composer.BackColor };
        composeLayout.RowStyles.Add(new RowStyle(SizeType.Percent,100)); composeLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100)); composeLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,68));
        input.BorderStyle = BorderStyle.None; input.BackColor = composer.BackColor; input.ForeColor = Color.FromArgb(239,234,255);
        input.Font = new Font("Segoe UI",16); input.ScrollBars = ScrollBars.None; input.Margin = new Padding(0,9,16,0);
        input.AccessibleName = "Ask anything";
        var inputHost = new Panel { Dock = DockStyle.Fill, BackColor = composer.BackColor };
        inputHost.Controls.Add(input);
        var placeholder = new Label { Text = "Ask anything.", AutoSize = true, Font = input.Font, ForeColor = Color.FromArgb(165,155,190), BackColor = input.BackColor, Location = new Point(1,9), Cursor = Cursors.IBeam };
        inputHost.Controls.Add(placeholder); placeholder.BringToFront(); placeholder.Click += delegate { input.Focus(); };
        input.TextChanged += delegate { placeholder.Visible = input.Text.Length == 0; };
        send.Text = "↑"; send.Font = new Font("Segoe UI",25); send.FlatStyle = FlatStyle.Flat; send.FlatAppearance.BorderSize = 0;
        send.BackColor = Color.FromArgb(163,139,255); send.ForeColor = Color.FromArgb(24,15,48); send.Cursor = Cursors.Hand;
        send.Margin = new Padding(1); send.Resize += delegate { var path = new System.Drawing.Drawing2D.GraphicsPath(); path.AddEllipse(0,0,send.Width-1,send.Height-1); var old = send.Region; send.Region = new Region(path); path.Dispose(); if(old != null) old.Dispose(); };
        composeLayout.Controls.Add(inputHost,0,0); composeLayout.Controls.Add(send,1,0); composer.Controls.Add(composeLayout); layout.Controls.Add(composer,0,2);
        status.Text = "Ready when you are."; status.ForeColor = Color.FromArgb(174,162,200); status.TextAlign = ContentAlignment.MiddleCenter;
        status.AutoSize = false; layout.Controls.Add(status,0,3);
        layout.Controls.Add(new Label { Text = "Enter to send  ·  Shift+Enter for a new line  ·  Powered by Gemini", Dock = DockStyle.Fill, ForeColor = Color.FromArgb(125,113,151), TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Segoe UI",9) },0,4);
        model.Items.Add("gemini-3.8-flash"); model.SelectedIndex = 0;
        Controls.Add(layout);
        send.Click += async delegate { await Send(); };
        input.KeyDown += async (sender,e) => { if (ShouldSend(e.KeyCode,e.Shift)) { e.SuppressKeyPress = true; await Send(); } };
        clear.Click += delegate { history.Clear(); chat.Clear(); Welcome(); status.Text = "New conversation started."; input.Focus(); };
        FormClosed += delegate { http.Dispose(); };
        Shown += delegate { input.Focus(); };
        Welcome();
    }
    static bool ShouldSend(Keys code, bool shift) { return code == Keys.Enter && !shift; }
    void Welcome() { Append("LET'S TALK", "What can I help you with?\n\nAsk a question, explore an idea, or make something new."); }
    void Append(string who, string message) { chat.SelectionStart = chat.TextLength; chat.SelectionColor = Color.FromArgb(179,155,255); chat.AppendText(who + "\n"); chat.SelectionColor = Color.WhiteSmoke; chat.AppendText(message + "\n\n"); chat.ScrollToCaret(); }
    void Busy(bool value) { busy = value; send.Enabled = refresh.Enabled = clear.Enabled = key.Enabled = model.Enabled = input.Enabled = !value; }
    string ApiKey() { var value = key.Text.Trim(); if (value.Length == 0) throw new Exception("Enter your Gemini API key first."); return value; }
    async Task<Dictionary<string,object>> Request(string path, object body)
    {
        using (var request = new HttpRequestMessage(body == null ? HttpMethod.Get : HttpMethod.Post, "https://generativelanguage.googleapis.com/v1beta/" + path))
        {
            request.Headers.Add("x-goog-api-key", ApiKey());
            if (body != null) request.Content = new StringContent(json.Serialize(body), Encoding.UTF8, "application/json");
            using (var response = await http.SendAsync(request))
            {
                string raw = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode) {
                    int code = (int)response.StatusCode;
                    string detail = "";
                    try {
                        var parsed = json.Deserialize<Dictionary<string,object>>(raw);
                        var apiError = (Dictionary<string,object>)parsed["error"];
                        detail = Convert.ToString(apiError["message"]).Replace(ApiKey(), "[redacted]");
                    } catch { }
                    if (detail.Length > 0) throw new Exception("Google HTTP " + code + ": " + detail);
                    throw new Exception(code == 429 ? "Google's usage limit was reached. Check your quota or try again later." : code == 400 || code == 401 || code == 403 ? "Google rejected the request. Check your API key, API access, and model permissions." : code == 404 ? "This model is unavailable. Click Load models and choose another model." : "Google returned HTTP " + code + ". Please try again later.");
                }
                return json.Deserialize<Dictionary<string,object>>(raw);
            }
        }
    }
    async Task LoadModels()
    {
        if (busy) return; Busy(true); status.Text = "Loading available models...";
        try {
            var names = new List<string>(); string page = "";
            do {
                var data = await Request("models?pageSize=100" + (page.Length > 0 ? "&pageToken=" + Uri.EscapeDataString(page) : ""),null);
                if (data.ContainsKey("models")) foreach (Dictionary<string,object> item in Items(data["models"])) {
                    if (item.ContainsKey("supportedGenerationMethods") && Items(item["supportedGenerationMethods"]).Any(x => (string)x == "generateContent")) names.Add(((string)item["name"]).Replace("models/", ""));
                }
                page = data.ContainsKey("nextPageToken") ? (string)data["nextPageToken"] : "";
            } while (page.Length > 0);
            if (names.Count == 0) throw new Exception("No chat models are available for this key.");
            string previous = model.Text; model.Items.Clear(); model.Items.AddRange(names.OrderBy(x => x).ToArray()); model.Text = names.Contains(previous) ? previous : names[0]; status.Text = "Models loaded. Ready to chat.";
        } catch (Exception ex) { Error(ex); } finally { Busy(false); }
    }
    static object[] Items(object value) { return ((System.Collections.IEnumerable)value).Cast<object>().ToArray(); }
    public static string Extract(Dictionary<string,object> data)
    {
        if (!data.ContainsKey("candidates")) throw new Exception("Google returned no answer. Try rephrasing your message.");
        var candidates = Items(data["candidates"]);
        if (candidates.Length == 0) throw new Exception("No answer was returned. Try rephrasing your message.");
        var candidate = (Dictionary<string,object>)candidates[0];
        if (!candidate.ContainsKey("content")) throw new Exception("The response was blocked or empty. Try a different message.");
        var content = (Dictionary<string,object>)candidate["content"];
        if (!content.ContainsKey("parts")) throw new Exception("The response contained no text.");
        var parts = Items(content["parts"]);
        string answer = string.Join("\n",parts.Cast<Dictionary<string,object>>().Where(p => p.ContainsKey("text") && (!p.ContainsKey("thought") || !(bool)p["thought"])).Select(p => (string)p["text"]).ToArray());
        if (string.IsNullOrWhiteSpace(answer)) throw new Exception("The response contained no text."); return answer;
    }
    async Task Send()
    {
        if (busy || string.IsNullOrWhiteSpace(input.Text)) return;
        string message = input.Text.Trim();
        try { ApiKey(); if (string.IsNullOrWhiteSpace(model.Text)) throw new Exception("Choose a model first."); } catch (Exception ex) { Error(ex); return; }
        Busy(true); status.Text = "Gemini is thinking...";
        try {
            var user = new { role = "user", parts = new [] { new { text = message } } };
            var pending = new List<object>(history); pending.Add(user);
            var result = await Request("models/" + Uri.EscapeDataString(model.Text.Trim().Replace("models/", "")) + ":generateContent",new { contents = pending });
            string answer = Extract(result);
            history.Add(user); history.Add(((Dictionary<string,object>)Items(result["candidates"])[0])["content"]);
            Append("You",message); Append("Gemini",answer); input.Clear(); status.Text = "Ready";
        } catch (Exception ex) { Error(ex); } finally { Busy(false); input.Focus(); }
    }
    void Error(Exception ex) { status.Text = ex is TaskCanceledException ? "Request timed out. Your message is still here; try again." : ex is HttpRequestException ? "Cannot connect to Google. Check your internet connection." : ex.Message; Append("Connection / API error", status.Text); }
    [STAThread] static int Main(string[] args)
    {
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        if (args.Length == 2 && args[0] == "--preview") {
            using (var window = new GeminiChat()) { window.Show(); Application.DoEvents(); using (var bitmap = new Bitmap(window.Width,window.Height)) { window.DrawToBitmap(bitmap,new Rectangle(0,0,window.Width,window.Height)); bitmap.Save(args[1]); } }
            return 0;
        }
        if (args.Contains("--self-test")) {
            try {
                var parser = new JavaScriptSerializer();
                string answer = Extract(parser.Deserialize<Dictionary<string,object>>("{\"candidates\":[{\"content\":{\"parts\":[{\"text\":\"hidden\",\"thought\":true},{\"text\":\"Hello\"},{\"text\":\"world\"}]}}]}"));
                if (answer != "Hello\nworld") return 1;
                bool rejected = false; try { Extract(parser.Deserialize<Dictionary<string,object>>("{\"candidates\":[]}")); } catch { rejected = true; }
                if (!rejected || !ShouldSend(Keys.Enter,false) || ShouldSend(Keys.Enter,true) || ShouldSend(Keys.A,false)) return 2;
                using (var window = new GeminiChat()) { window.CreateControl(); if (string.IsNullOrWhiteSpace(window.key.Text) || window.history.Count != 0) return 3; }
                return 0;
            } catch { return 4; }
        }
        Application.Run(new GeminiChat()); return 0;
    }
}

class RoundedPanel : Panel
{
    public RoundedPanel() { DoubleBuffered = true; }
    protected override void OnPaintBackground(PaintEventArgs e) {
        e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        using (var path = new System.Drawing.Drawing2D.GraphicsPath()) {
            int d = 58; var r = new Rectangle(1,1,Width-3,Height-3);
            path.AddArc(r.X,r.Y,d,d,180,90); path.AddArc(r.Right-d,r.Y,d,d,270,90); path.AddArc(r.Right-d,r.Bottom-d,d,d,0,90); path.AddArc(r.X,r.Bottom-d,d,d,90,90); path.CloseFigure();
            using(var background = new SolidBrush(Parent.BackColor)) e.Graphics.FillRectangle(background,ClientRectangle);
            using(var fill = new SolidBrush(BackColor)) e.Graphics.FillPath(fill,path);
            using(var border = new Pen(Color.FromArgb(79,64,118))) e.Graphics.DrawPath(border,path);
        }
    }
}
