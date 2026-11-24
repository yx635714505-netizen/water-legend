using System;
using System.IO;
using System.Diagnostics;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.Geometry;
using Exception=System.Exception;
using System.Runtime.InteropServices;

public class CadPoolBridge {
 [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
 static string Root {get{return Environment.GetEnvironmentVariable("CAD_POOL_JOB");}}
 static string Job {get{return Environment.GetEnvironmentVariable("CAD_POOL_JOB_ID");}}
 static JavaScriptSerializer Json=new JavaScriptSerializer();
 static System.Windows.Forms.Timer timer;
 static void Write(string name,object data) {
  string path=Path.Combine(Root,"control",name),temp=path+".tmp";
  File.WriteAllText(temp,Json.Serialize(data));
  if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);
 }
 static string Inside(string relative) {
  string path=Path.GetFullPath(Path.Combine(Root,relative));
  if(!path.StartsWith(Path.GetFullPath(Root)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Path escapes job directory");
  return path;
 }
 [CommandMethod("CADPOOLREADY")]
 public void Ready() {
  Application.SetSystemVariable("FILEDIA",0);Application.SetSystemVariable("CMDDIA",0);
  Application.SetSystemVariable("BACKGROUNDPLOT",0);
  Application.SetSystemVariable("SAVEFILEPATH",Path.Combine(Root,"autosave"));
  Application.SetSystemVariable("LOGFILEPATH",Path.Combine(Root,"logs"));
  timer=new System.Windows.Forms.Timer();timer.Interval=2000;
  timer.Tick+=(s,e)=>{try{Write("heartbeat.json",new {jobId=Job,pid=Process.GetCurrentProcess().Id,utc=DateTime.UtcNow.ToString("o")});}catch{}};timer.Start();
  Write("ready.json",new {jobId=Job,pid=Process.GetCurrentProcess().Id,slot=Environment.GetEnvironmentVariable("CAD_POOL_SLOT"),profile=Application.GetSystemVariable("CPROFILE"),temp=Path.GetTempPath(),utc=DateTime.UtcNow.ToString("o")});
 }
 static void Finish(bool ok,string message) {
  Write("result.json",new {jobId=Job,pid=Process.GetCurrentProcess().Id,success=ok,message=message,utc=DateTime.UtcNow.ToString("o")});
  // Disposable worker: outputs and validation must already be saved and closed.
  // Do not run interactive QUIT/save/profile dialogs on the hidden desktop.
  // Native Tianzheng unload hooks can block even Environment.Exit. This handle
  // is the current disposable worker only; all durable task files are closed.
  if(!TerminateProcess(GetCurrentProcess(),0))throw new System.ComponentModel.Win32Exception();
 }
 [CommandMethod("CADPOOLCOMPLETE")]
 public void Complete() {
  try {
   var manifest=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(Root,"job.json")));
   var report=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Inside((string)manifest["validationReport"])));
   if(!report.ContainsKey("passed")||!Convert.ToBoolean(report["passed"])||!report.ContainsKey("jobId")||(string)report["jobId"]!=Job)throw new Exception("Validation report missing, failed, or belongs to another job");
   foreach(object entry in (System.Collections.IEnumerable)manifest["expectedOutputs"]){string p=Inside((string)entry);if(!File.Exists(p)||new FileInfo(p).Length==0)throw new Exception("Missing output: "+p);}
   Finish(true,"Task report passed; inspect report for scope of validation.");
  }catch(Exception e){Finish(false,e.ToString());}
 }
 [CommandMethod("CADPOOLFAIL")]
 public void Fail(){Finish(false,"Intentional failure or task requested failure.");}
 [CommandMethod("CADPOOLSMOKE")]
 public void Smoke(){
  try {
   System.Threading.Thread.Sleep(15000);
   string src=Path.Combine(Root,"input","native.dwg"),outFile=Path.Combine(Root,"output","native-copy.dwg");int native=0,proxies=0,readBack=0;
   using(var db=new Database(false,true)) {
    db.ReadDwgFile(src,FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
    using(var tx=db.TransactionManager.StartTransaction()) {
     var bt=(BlockTable)tx.GetObject(db.BlockTableId,OpenMode.ForRead);
     foreach(ObjectId bid in bt)foreach(ObjectId id in (BlockTableRecord)tx.GetObject(bid,OpenMode.ForRead)){
      var obj=tx.GetObject(id,OpenMode.ForRead);if(obj.GetRXClass().DxfName.StartsWith("TCH_"))native++;if(obj is ProxyEntity)proxies++;
     }
    }
    db.SaveAs(outFile,DwgVersion.AC1032);
   }
   using(var db=new Database(false,true)) {
    db.ReadDwgFile(outFile,FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
    using(var tx=db.TransactionManager.StartTransaction())foreach(ObjectId bid in (BlockTable)tx.GetObject(db.BlockTableId,OpenMode.ForRead))foreach(ObjectId id in (BlockTableRecord)tx.GetObject(bid,OpenMode.ForRead))if(tx.GetObject(id,OpenMode.ForRead).GetRXClass().DxfName.StartsWith("TCH_"))readBack++;
   }
   File.WriteAllText(Path.Combine(Root,"output","validation.json"),Json.Serialize(new {jobId=Job,passed=native>0&&readBack==native&&proxies==0,scope="concurrent native load/save/readback only; not project design QA",nativeCount=native,readBackCount=readBack,proxyCount=proxies}));
   Complete();
  }catch(Exception e){Finish(false,e.ToString());}
 }
}
