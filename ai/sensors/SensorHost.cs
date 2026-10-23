using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Threading;
using System.Web.Script.Serialization;
using LibreHardwareMonitor.Hardware;
class SensorHost {
 static volatile bool stop=false;
 static readonly JavaScriptSerializer json=new JavaScriptSerializer();
 static readonly ConcurrentQueue<string> commands=new ConcurrentQueue<string>();
 static readonly List<object> rows=new List<object>(), fans=new List<object>(), controls=new List<object>();
 static readonly Dictionary<string,IControl> available=new Dictionary<string,IControl>(), owned=new Dictionary<string,IControl>();
 static DateTime lease=DateTime.UtcNow;
 static float hottest=0;
 static void Emit(object value){Console.WriteLine(json.Serialize(value));Console.Out.Flush();}
 static string Category(HardwareType type){string text=type.ToString().ToLowerInvariant();if(text.Contains("cpu"))return "CPU";if(text.Contains("gpu"))return "GPU";if(text.Contains("memory"))return "Memory";if(text.Contains("storage"))return "Storage";return "Motherboard";}
 static bool IsLive(string name){string text=name.ToLowerInvariant();return !text.Contains("warning temperature")&&!text.Contains("critical temperature")&&!text.Contains("threshold")&&!text.Contains("distance to")&&!text.Contains("tjmax")&&!text.Contains("temperature limit");}
 static void Read(IHardware hardware,string part){try{hardware.Update();foreach(var sensor in hardware.Sensors){string id=sensor.Identifier.ToString();
  if(sensor.SensorType==SensorType.Temperature&&IsLive(sensor.Name)&&sensor.Value.HasValue&&sensor.Value.Value>0&&sensor.Value.Value<160){rows.Add(new{part=part,hardware=hardware.Name,id=id,name=hardware.Name+" / "+sensor.Name,c=sensor.Value.Value,source="LibreHardwareMonitor"});if(part=="CPU"||part=="GPU")hottest=Math.Max(hottest,sensor.Value.Value);}
  if(sensor.SensorType==SensorType.Fan)fans.Add(new{id=id,name=sensor.Name,hardware=hardware.Name,rpm=sensor.Value});
  if(sensor.SensorType==SensorType.Control&&sensor.Control!=null&&!sensor.Name.ToLowerInvariant().Contains("pump")){
   available[id]=sensor.Control;controls.Add(new{id=id,name=sensor.Name,hardware=hardware.Name,value=sensor.Value,min=Math.Max(30,sensor.Control.MinSoftwareValue),max=Math.Min(100,sensor.Control.MaxSoftwareValue),manual=owned.ContainsKey(id)});
  }
 }foreach(var child in hardware.SubHardware)Read(child,part);}catch{}}
 static void Restore(){foreach(var pair in new Dictionary<string,IControl>(owned)){try{pair.Value.SetDefault();owned.Remove(pair.Key);}catch{}}}
 static void ProcessCommands(){string line;while(commands.TryDequeue(out line)){try{
  var command=json.Deserialize<Dictionary<string,object>>(line);string op=Convert.ToString(command["op"]);
  if(op=="heartbeat"){lease=DateTime.UtcNow;continue;}
  if(op=="restore_all"){Restore();Emit(new{kind="fan_result",ok=owned.Count==0,message=owned.Count==0?"Hardware automatic control restored.":"Some controls could not be restored. Retry automatic control."});continue;}
  if(op=="manual_many"||op=="default_many"){
   var ids=new List<string>();foreach(var item in (System.Collections.IEnumerable)command["ids"]){string key=Convert.ToString(item);if(!ids.Contains(key))ids.Add(key);}
   if(ids.Count==0)throw new Exception("No fan controllers selected.");
   float duty=op=="manual_many"?Convert.ToSingle(command["value"]):0;
   foreach(string key in ids){
    if(!available.ContainsKey(key))throw new Exception("A selected fan controller is no longer available.");
    var c=available[key];
    if(op=="manual_many"&&(float.IsNaN(duty)||float.IsInfinity(duty)||duty<Math.Max(30,c.MinSoftwareValue)||duty>Math.Min(100,c.MaxSoftwareValue)))throw new Exception("Duty is outside the shared controller range.");
   }
   if(op=="manual_many"&&(hottest<=0||hottest>=85))throw new Exception("Manual control requires live CPU/GPU temperatures below 85°C.");
   var changed=new List<string>();
   try{
    foreach(string key in ids){var c=available[key];changed.Add(key);if(op=="manual_many"){owned[key]=c;c.SetSoftware(duty);}else{c.SetDefault();owned.Remove(key);}}
   }catch{foreach(string key in changed){try{available[key].SetDefault();owned.Remove(key);}catch{}}throw;}
   lease=DateTime.UtcNow;Emit(new{kind="fan_result",ok=true,message=op=="manual_many"?"Manual duty "+duty+"% applied to "+ids.Count+" fan controllers.":"Automatic control restored for "+ids.Count+" fan controllers."});continue;
  }
  string id=Convert.ToString(command["id"]);if(!available.ContainsKey(id))throw new Exception("Fan controller no longer available.");IControl control=available[id];
  if(op=="default"){control.SetDefault();owned.Remove(id);Emit(new{kind="fan_result",ok=true,message="Hardware automatic control restored."});}
  else if(op=="manual"){
   float value=Convert.ToSingle(command["value"]);float minimum=Math.Max(30,control.MinSoftwareValue),maximum=Math.Min(100,control.MaxSoftwareValue);
   if(float.IsNaN(value)||float.IsInfinity(value)||value<minimum||value>maximum)throw new Exception("Duty must stay within the supported 30–100% range.");
   if(hottest<=0||hottest>=85)throw new Exception("Manual control needs a live CPU/GPU temperature below 85°C.");
   owned[id]=control;try{control.SetSoftware(value);}catch{try{control.SetDefault();owned.Remove(id);}catch{}throw;}
   lease=DateTime.UtcNow;Emit(new{kind="fan_result",ok=true,message="Manual fan duty sent: "+value+"%."});
  }else throw new Exception("Unknown fan command.");
 }catch(Exception ex){Emit(new{kind="fan_result",ok=false,message=ex.Message});}}}
 static void Main(string[] args){if(Array.IndexOf(args,"--verify")>=0){Console.WriteLine(typeof(Computer).Assembly.GetName().Version.ToString());return;}
 var computer=new Computer{IsCpuEnabled=true,IsGpuEnabled=true,IsMemoryEnabled=true,IsMotherboardEnabled=true,IsStorageEnabled=true,IsControllerEnabled=true};
 var reader=new Thread(()=>{try{string line;while((line=Console.ReadLine())!=null){if(line=="close")break;commands.Enqueue(line);}}catch{}stop=true;});reader.IsBackground=true;reader.Start();
 try{computer.Open();if(Array.IndexOf(args,"--diagnose")>=0){foreach(var h in computer.Hardware)h.Update();System.IO.File.WriteAllText(args[args.Length-1],computer.GetReport());return;}
 if(Array.IndexOf(args,"--snapshot")>=0){foreach(var hardware in computer.Hardware)Read(hardware,Category(hardware.HardwareType));System.IO.File.WriteAllText(args[args.Length-1],json.Serialize(new{kind="hardware",temperatures=rows,fans=fans,controls=controls}));return;}
 while(!stop){rows.Clear();fans.Clear();controls.Clear();available.Clear();hottest=0;foreach(var hardware in computer.Hardware)Read(hardware,Category(hardware.HardwareType));
  if(owned.Count>0&&(hottest<=0||hottest>=85||(DateTime.UtcNow-lease).TotalSeconds>45)){Restore();Emit(new{kind="fan_result",ok=false,message="Manual control ended: temperature protection or monitor disconnected. Hardware automatic control restoration requested."});}
  ProcessCommands();Emit(new{kind="hardware",temperatures=rows,fans=fans,controls=controls});
  for(int i=0;i<5&&!stop;i++)Thread.Sleep(200);
 }}catch(Exception ex){Emit(new{error=ex.Message});}finally{Restore();computer.Close();}
 }
}
