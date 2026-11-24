using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Threading;

// Keeps desktop/process handles alive until CAD exits. Never attaches to a user's CAD.
public class HiddenCad {
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct SI {
  public int cb; public string reserved,desktop,title; public int x,y,w,h,cx,cy,fill,flags;
  public short show,cbReserved; public IntPtr reserved2,input,output,error;
 }
 [StructLayout(LayoutKind.Sequential)] struct PI {public IntPtr process,thread;public int pid,tid;}
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateDesktop(string n,IntPtr d,IntPtr m,int f,uint a,IntPtr s);
 [DllImport("user32.dll")] static extern bool CloseDesktop(IntPtr h);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string a,string c,IntPtr p,IntPtr t,bool i,uint f,IntPtr e,string w,ref SI s,out PI pi);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h,uint ms);
 [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr h,out uint code);
 [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h,uint code);
 static JavaScriptSerializer json=new JavaScriptSerializer();
 static void Write(string path,object value) {string tmp=path+".tmp";File.WriteAllText(tmp,json.Serialize(value));File.Move(tmp,path);}
 static string Quote(string s) {if(s.Contains("\""))throw new Exception("Invalid argument");return "\""+s+"\"";}
 public static int Main(string[] args) {
  string root=Path.GetFullPath(args[0]); IntPtr desktop=IntPtr.Zero;PI pi=new PI();bool started=false;
  try {
   Write(Path.Combine(root,"control","launcher.json"),new {pid=Process.GetCurrentProcess().Id,started=Process.GetCurrentProcess().StartTime.ToUniversalTime().ToString("o")});
   var cfg=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(root,"launch.json")));
   string slot=(string)cfg["slot"], job=(string)cfg["jobId"];
   using(var mutex=new Mutex(false,"Local\\CodexCAD_"+slot)) {
    bool held=false;try {try{held=mutex.WaitOne(0);}catch(AbandonedMutexException){held=true;}
     if(!held)throw new Exception("Worker is already owned: "+slot);
     Environment.SetEnvironmentVariable("TEMP",Path.Combine(root,"temp"));
     Environment.SetEnvironmentVariable("TMP",Path.Combine(root,"temp"));
     Environment.SetEnvironmentVariable("CAD_POOL_JOB",root);
     Environment.SetEnvironmentVariable("CAD_POOL_JOB_ID",job);
     Environment.SetEnvironmentVariable("CAD_POOL_SLOT",slot);
     string desk="CodexCAD_"+slot+"_"+job;
     desktop=CreateDesktop(desk,IntPtr.Zero,IntPtr.Zero,0,0x10000000,IntPtr.Zero);
     if(desktop==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();
     var si=new SI();si.cb=Marshal.SizeOf(si);si.desktop="winsta0\\"+desk;si.flags=1;si.show=0;
     string exe=(string)cfg["acadExe"];
     string cmd=Quote(exe)+" /nologo /p "+Quote((string)cfg["profile"])+" /t "+Quote((string)cfg["template"])+" /b "+Quote(Path.Combine(root,"scripts","boot.scr"));
     if(!CreateProcess(exe,cmd,IntPtr.Zero,IntPtr.Zero,false,0,IntPtr.Zero,root,ref si,out pi))throw new System.ComponentModel.Win32Exception();
     started=true;CloseHandle(pi.thread);pi.thread=IntPtr.Zero;
     Write(Path.Combine(root,"control","process.json"),new {jobId=job,slot=slot,pid=pi.pid,launcherPid=Process.GetCurrentProcess().Id,desktop=desk,commandLine=cmd});
     var timer=Stopwatch.StartNew();double timeout=Convert.ToDouble(cfg["timeoutSeconds"]);
     bool killed=false;
     while(WaitForSingleObject(pi.process,500)==258) {
      if(File.Exists(Path.Combine(root,"control","stop.request"))||timer.Elapsed.TotalSeconds>timeout){TerminateProcess(pi.process,124);killed=true;WaitForSingleObject(pi.process,30000);break;}
     }
     uint exitCode;GetExitCodeProcess(pi.process,out exitCode);
     Write(Path.Combine(root,"control","exit.json"),new {jobId=job,pid=pi.pid,exitCode=exitCode,terminated=killed});
     return killed?124:(int)exitCode;
    } finally {if(held)mutex.ReleaseMutex();}
   }
  } catch(Exception e) {
   if(started&&pi.process!=IntPtr.Zero){TerminateProcess(pi.process,125);WaitForSingleObject(pi.process,30000);}
   File.WriteAllText(Path.Combine(root,"control","launcher_error.txt"),e.ToString());return 125;
  } finally {if(pi.process!=IntPtr.Zero)CloseHandle(pi.process);if(pi.thread!=IntPtr.Zero)CloseHandle(pi.thread);if(desktop!=IntPtr.Zero)CloseDesktop(desktop);}
 }
}
