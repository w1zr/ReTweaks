// Explicitly opt-in diagnostic: sends only one tiny test prompt, never PC data/history.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
class CheckService {
    static string credential;
    static HttpClient client;
    static string stage="startup",selectedModel="";
    static object Call(object form,string path,object payload) {
        var json=new JavaScriptSerializer();
        using(var request=new HttpRequestMessage(payload==null ? HttpMethod.Get : HttpMethod.Post,"https://generativelanguage.googleapis.com/v1beta/"+path)) {
            request.Headers.Add("x-goog-api-key",credential);
            if(payload!=null)request.Content=new StringContent(json.Serialize(payload),System.Text.Encoding.UTF8,"application/json");
            using(var response=client.SendAsync(request).GetAwaiter().GetResult()) {
                string raw=response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                var data=json.Deserialize<Dictionary<string,object>>(raw);
                if(!response.IsSuccessStatusCode) {
                    string message="Google returned HTTP "+(int)response.StatusCode;
                    if(data.ContainsKey("error"))message+=": "+Convert.ToString(((Dictionary<string,object>)data["error"])["message"]);
                    throw new Exception(message.Replace(credential,"[redacted]"));
                }
                return data;
            }
        }
    }
    [STAThread] static void Main() {
        string key="";var json=new JavaScriptSerializer();
        try {
            ServicePointManager.SecurityProtocol=(SecurityProtocolType)3072;
            var assembly=Assembly.LoadFrom(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"GeminiChat.exe"));
            using(var form=(Form)Activator.CreateInstance(assembly.GetType("GeminiChat",true))) {
                key=(string)form.GetType().GetMethod("ApiKey",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(form,null);
                credential=key;client=new HttpClient();client.Timeout=TimeSpan.FromSeconds(55);
                stage="list_models";
                var models=(Dictionary<string,object>)Call(form,"models?pageSize=1000",null);
                var names=new List<string>();
                foreach(Dictionary<string,object> model in (IEnumerable)models["models"]) {
                    string name=Convert.ToString(model["name"]);bool generate=false;
                    if(model.ContainsKey("supportedGenerationMethods"))foreach(object method in (IEnumerable)model["supportedGenerationMethods"])if(Convert.ToString(method)=="generateContent")generate=true;
                    if(generate && name.Contains("gemini") && name.Contains("flash") && !name.Contains("image") && !name.Contains("tts") && !name.Contains("live"))names.Add(name);
                }
                names.Sort(StringComparer.Ordinal);names.Reverse();
                if(names.Count==0)throw new Exception("No text-generation model is available to this credential.");
                string selected=names.Find(n=>n.Contains("flash-lite") && !n.Contains("preview")) ?? names.Find(n=>n.EndsWith("flash-latest")) ?? names[0];
                selectedModel=selected;stage="generate_reply";
                var payload=new {contents=new[]{new {role="user",parts=new[]{new {text="Reply exactly OK."}}}},generationConfig=new {maxOutputTokens=2048}};
                var response=Call(form,selected+":generateContent",payload);
                string reply=(string)form.GetType().GetMethod("Extract",BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new[]{response});
                Console.WriteLine(json.Serialize(new {ok=!String.IsNullOrWhiteSpace(reply),model=selected,reply=reply}));
            }
        } catch(Exception ex) {
            while(ex is TargetInvocationException && ex.InnerException!=null)ex=ex.InnerException;
            string message=ex.Message;if(key.Length>0)message=message.Replace(key,"[redacted]");
                Console.WriteLine(json.Serialize(new {ok=false,stage=stage,model=selectedModel,error=message.Length>400?message.Substring(0,400):message}));
            Environment.ExitCode=1;
        }
    }
}
