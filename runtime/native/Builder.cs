using System;using System.Collections.Generic;using System.Linq;using System.IO;using System.Runtime.InteropServices;using System.Web.Script.Serialization;using Autodesk.AutoCAD.DatabaseServices;using Autodesk.AutoCAD.ApplicationServices;using Autodesk.AutoCAD.EditorInput;using Autodesk.AutoCAD.Geometry;using Autodesk.AutoCAD.Runtime;using Autodesk.AutoCAD.PlottingServices;
public class Builder {
const string K="tch_kernal.arx",W="tch_pipewire.arx";
[DllImport(K,EntryPoint="?SetLabelVisible@TDbOpening@@QEAAX_N@Z")]static extern void Opening(IntPtr e,[MarshalAs(UnmanagedType.I1)]bool visible);
[DllImport(K,EntryPoint="?SetText@TDbText@@QEAAXPEB_W@Z",CharSet=CharSet.Unicode)]static extern void TextSet(IntPtr e,string s);
[DllImport(K,EntryPoint="?SetText1@TDbSymbMultiLeader@@QEAAXPEB_W@Z",CharSet=CharSet.Unicode)]static extern void L1(IntPtr e,string s);
[DllImport(K,EntryPoint="?SetText2@TDbSymbMultiLeader@@QEAAXPEB_W@Z",CharSet=CharSet.Unicode)]static extern void L2(IntPtr e,string s);
[DllImport(W,EntryPoint="?SetDnDiameter@TDbPipe@@QEAAXN@Z")]static extern void Diameter(IntPtr e,double dia);
[DllImport(W,EntryPoint="?GetDnDiameter@TDbPipe@@QEBANXZ")]public static extern double ReadDn(IntPtr e);
[DllImport(W,EntryPoint="?SetLabel@TDbPipe@@QEAAXPEB_W@Z",CharSet=CharSet.Unicode)]static extern void Prefix(IntPtr e,string s);
[DllImport(W,EntryPoint="?SetStartPoint@TDbPipePrototype@@QEAAXAEBVTADSGePoint3d@@HH@Z")]static extern void Start(IntPtr e,ref Point3d pt,int a,int b);
[DllImport(W,EntryPoint="?SetEndPoint@TDbPipePrototype@@QEAAXAEBVTADSGePoint3d@@HH@Z")]static extern void End(IntPtr e,ref Point3d pt,int a,int b);
[DllImport(W,EntryPoint="?SetLabelLocation@TDbPipePrototype@@QEAAXAEBVTADSGePoint3d@@@Z")]static extern void LabelLoc(IntPtr e,ref Point3d pt);
[DllImport(W,EntryPoint="?EnableDrawLabel@TDbPipePrototype@@QEAAXH@Z")]static extern void DrawLabel(IntPtr e,int draw);
[DllImport(W,EntryPoint="?SetTextHeight@TDbPipePrototype@@QEAAXN@Z")]static extern void PipeTextHeight(IntPtr e,double ht);
public class Base { public string[] ids; public string name, source; public double dx,dy; public bool fade; public Dictionary<string,string> text; }
public class Frame { public string name; public double[] b; public double scale; }
public class Sample { public string source, handle; }
public class Chain { public double x,labelX; public double[] levels; }
public class Config { public Base[] bases; public Frame[] frames; public Op[] ops; public Chain[] dimensions; public Dictionary<string,Sample> symbols; }
static string root=Environment.GetEnvironmentVariable("CAD_POOL_JOB"),outp=root+"/output/";static JavaScriptSerializer js=new JavaScriptSerializer(){MaxJsonLength=int.MaxValue};static Config cfg {get{return js.Deserialize<Config>(File.ReadAllText(root+"/scripts/cfg.json").Replace("\"base\":","\"bases\":"));}}
static ObjectId Id(Database d,string h){return d.GetObjectId(false,new Handle(Convert.ToInt64(h,16)),0);}static Entity E(Transaction t,Database d,string h){return (Entity)t.GetObject(Id(d,h),OpenMode.ForWrite);}static ObjectId model(Database d){return SymbolUtilityServices.GetBlockModelSpaceId(d);}static void log(string s){File.AppendAllText(outp+"progress.txt",s+Environment.NewLine);}
static Point3dCollection Grips(Entity e){var p=new Point3dCollection();e.GetGripPoints(p,new IntegerCollection(),new IntegerCollection());return p;}
static void move(Entity e,double x,double y){e.TransformBy(Matrix3d.Displacement(new Vector3d(x,y,0)));}
static void Fade(Transaction t,ObjectId id,HashSet<ObjectId> seen){if(!seen.Add(id))return;var b=(BlockTableRecord)t.GetObject(id,OpenMode.ForRead);foreach(ObjectId i in b){var e=t.GetObject(i,OpenMode.ForWrite) as Entity;if(e==null)continue;bool col=e.Layer.EndsWith("A-立面看线")||e.GetRXClass().DxfName=="TCH_COLUMN";if(col){e.Layer="0";e.Visible=true;if(e is Polyline)e.Linetype="Continuous";}e.Color=Autodesk.AutoCAD.Colors.Color.FromRgb(155,155,155);e.LineWeight=col?LineWeight.LineWeight025:LineWeight.LineWeight009;if(e.GetRXClass().DxfName=="TCH_OPENING"){Opening(e.UnmanagedObject,false);e.RecordGraphicsModified(true);}var br=e as BlockReference;if(br!=null)Fade(t,br.BlockTableRecord,seen);}}
static Database read(string file){var db=new Database(false,true);db.ReadDwgFile(file,FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);return db;}
static void InsertBase(Database d,Database ar,Base ba){ObjectId bid;using(var t=d.TransactionManager.StartTransaction()){var bt=(BlockTable)t.GetObject(d.BlockTableId,OpenMode.ForWrite);var b=new BlockTableRecord(){Name=ba.name};bid=bt.Add(b);t.AddNewlyCreatedDBObject(b,true);t.Commit();}
var mapping=new IdMapping();
ar.WblockCloneObjects(new ObjectIdCollection(ba.ids.Select(h=>Id(ar,h)).ToArray()),bid,mapping,DuplicateRecordCloning.MangleName,false);
using(var t=d.TransactionManager.StartTransaction()){
if(ba.text!=null) foreach(var kv in ba.text) SetTxt((Entity)t.GetObject(mapping[Id(ar,kv.Key)].Value,OpenMode.ForWrite),kv.Value);
if(ba.fade) Fade(t,bid,new HashSet<ObjectId>());
var br=new BlockReference(new Point3d(ba.dx,ba.dy,0),bid);var ms=(BlockTableRecord)t.GetObject(model(d),OpenMode.ForWrite);ms.AppendEntity(br);t.AddNewlyCreatedDBObject(br,true);var order=(DrawOrderTable)t.GetObject(ms.DrawOrderTableId,OpenMode.ForWrite);order.MoveToBottom(new ObjectIdCollection(new[]{br.ObjectId}));t.Commit();}log(ba.name);}
static Entity clone(Transaction t,BlockTableRecord ms,Entity e){var n=(Entity)e.Clone();ms.AppendEntity(n);t.AddNewlyCreatedDBObject(n,true);return n;}
static void leader(Transaction t,Database d,BlockTableRecord ms,string sample,string line1,string line2,double x,double y,string layer){var e=clone(t,ms,E(t,d,sample));var a=Grips(e)[2];move(e,x-a.X,y-a.Y);L1(e.UnmanagedObject,line1);L2(e.UnmanagedObject,line2);e.Layer=layer;e.RecordGraphicsModified(true);}
[DllImport(K,EntryPoint="?SetTextBaseLen@TDbSymbMultiLeader@@QEAAXNH@Z")]static extern void BaseLen(IntPtr e,double len,int which);
static IEnumerable<Extents3d> TextBoxes(Entity e,int depth){if(e is DBText||e is MText){yield return e.GeometricExtents;yield break;}if(depth>4)yield break;var objects=new DBObjectCollection();try{e.Explode(objects);}catch{yield break;}foreach(DBObject o in objects){var en=o as Entity;if(en!=null&&(en.GetRXClass().DxfName.Contains("TEXT")||depth==0)){foreach(var ex in TextBoxes(en,depth+1))yield return ex;}o.Dispose();}}
static Extents3d TextBox(Entity e){var boxes=TextBoxes(e,0).ToList();if(boxes.Count==0)throw new InvalidDataException("No visible text "+e.Handle);var result=boxes[0];foreach(var b in boxes.Skip(1))result.AddExtents(b);return result;}
[DllImport(K,EntryPoint="?GetTextBaseLen@TDbSymbMultiLeader@@QEBANH@Z")]static extern double ReadLen(IntPtr e,int which);
[DllImport(K,EntryPoint="?SetPageWidth@TDbSymbMultiLeader@@QEAAXNH@Z")]static extern void PageWidth(IntPtr e,double len,int mode);
public class Op {public string t,h,txt,txt2,layer;public double[] a,b,label;public int idx;public double dn,rot;public bool show,left;}
[DllImport(K,EntryPoint="?SetText@TDbSymbElevation@@QEAAXPEB_W@Z",CharSet=CharSet.Unicode)]static extern void SetE(IntPtr e,string val);
[DllImport(K,EntryPoint="?SetText@TDbSymbArrow@@QEAAXPEB_W@Z",CharSet=CharSet.Unicode)]static extern void SetA(IntPtr e,string val);
[DllImport(W,EntryPoint="?SetWellName@TDbWell@@QEAAXPEB_W@Z",CharSet=CharSet.Unicode)]static extern void WellName(IntPtr e,string val);
[DllImport(K,EntryPoint="??0TWCString@@QEAA@H@Z")]static extern IntPtr StrNew(IntPtr p,int length);
[DllImport(K,EntryPoint="??4TWCString@@QEAAAEAV0@PEB_W@Z",CharSet=CharSet.Unicode)]static extern IntPtr StrAssign(IntPtr p,string text);
[DllImport(K,EntryPoint="??1TWCString@@QEAA@XZ")]static extern void StrFree(IntPtr p);
[DllImport(K,EntryPoint="?SetNameText@TDbDrawingName@@QEAAXAEBVTWCString@@@Z")]static extern void TitleName(IntPtr p,IntPtr text);
[UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int ChangeText(IntPtr input,IntPtr output,IntPtr user);
[DllImport(K,EntryPoint="?ConvertText@TDbDrawingName@@UEAAHP6AHPEB_WAEAVTWCString@@PEAX@Z2@Z")]static extern int ConvertTitle(IntPtr p,ChangeText change,IntPtr user);
[DllImport(K,EntryPoint="?GetNameText@TDbDrawingName@@QEBA?AVTWCString@@XZ")]static extern IntPtr ReadTitle(IntPtr p,IntPtr result);
static void SetTitle(Entity e,string title){log("rename "+title);var mem=Marshal.AllocHGlobal(128);ReadTitle(e.UnmanagedObject,mem);try{StrAssign(mem,title);TitleName(e.UnmanagedObject,mem);e.RecordGraphicsModified(true);}finally{StrFree(mem);Marshal.FreeHGlobal(mem);}log("renamed "+title);}
[DllImport(W,EntryPoint="?SetLabelLocation@TDbWell@@QEAAXAEBVTADSGePoint3d@@@Z")]static extern void WellLabel(IntPtr e,ref Point3d p);
static void SetTxt(Entity e,string val){var tx=e as DBText;if(tx!=null)tx.TextString=val;else if(e.GetRXClass().DxfName=="TCH_TEXT")TextSet(e.UnmanagedObject,val);else throw new System.Exception("text class "+e.Handle);e.RecordGraphicsModified(true);}
static ObjectId imp(Database d,Database s,string h){var m=new IdMapping();var id=Id(s,h);s.WblockCloneObjects(new ObjectIdCollection(new[]{id}),model(d),m,DuplicateRecordCloning.MangleName,false);return m[id].Value;}
static readonly Dictionary<string,string> samples=new Dictionary<string,string>{
 {"JPLAN","84101"},{"JSYS","85A47"},{"WPLAN","85267"},{"WSYS","85BC5"},{"FPLAN","85B92"},{"FSYS","85A81"},{"YPLAN","85344"},{"YSYS","85C53"},{"JDOT","8411B"},{"WDOT","84144"},{"YDOT","85287"},{"FDOT","84DD2"}};
static Dictionary<string,ObjectId> ImportStyles(Database db){var dest=new Dictionary<string,ObjectId>();using(var style=read(root+"/input/style.dwg")){using(var st=style.TransactionManager.StartTransaction()){    var src=samples.ToDictionary(v=>v.Key,v=>(Entity)st.GetObject(Id(style,v.Value),OpenMode.ForRead));
    var layers=(LayerTable)st.GetObject(style.LayerTableId,OpenMode.ForRead);
    var lts=(LinetypeTable)st.GetObject(style.LinetypeTableId,OpenMode.ForRead);
    var names=new HashSet<string>(src.Values.Select(e=>e.Layer));names.Add("EQUIP_雨水");names.Add("EQUIP_废水");
    var types=new HashSet<string>(src.Values.Select(e=>e.Linetype));
    foreach(var name in names){if(!layers.Has(name))continue;var layer=(LayerTableRecord)st.GetObject(layers[name],OpenMode.ForRead);types.Add(((LinetypeTableRecord)st.GetObject(layer.LinetypeObjectId,OpenMode.ForRead)).Name);}
    foreach(var name in types){if(new[]{"Continuous","ByLayer","ByBlock"}.Contains(name,StringComparer.OrdinalIgnoreCase))continue;style.WblockCloneObjects(new ObjectIdCollection(new[]{lts[name]}),db.LinetypeTableId,new IdMapping(),DuplicateRecordCloning.Replace,false);}
    foreach(var name in names)if(layers.Has(name))style.WblockCloneObjects(new ObjectIdCollection(new[]{layers[name]}),db.LayerTableId,new IdMapping(),DuplicateRecordCloning.Replace,false);
    db.Ltscale=style.Ltscale;db.Celtscale=style.Celtscale;
foreach(var pair in samples.Concat(new[]{new KeyValuePair<string,string>("BOWL","85C52")})){var id=Id(style,pair.Value);var map=new IdMapping();style.WblockCloneObjects(new ObjectIdCollection(new[]{id}),model(db),map,DuplicateRecordCloning.Ignore,false);dest[pair.Key]=map[id].Value;}}}return dest;}static void Build(Database d){
 var c=cfg;
 foreach(var ba in c.bases) using(var src=read(root+"/input/"+ba.source+".dwg")) InsertBase(d,src,ba);
 HashSet<ObjectId> before;using(var tx=d.TransactionManager.StartTransaction()){before=new HashSet<ObjectId>(((BlockTableRecord)tx.GetObject(model(d),OpenMode.ForRead)).Cast<ObjectId>());} var prototypes=ImportStyles(d);
 foreach(var kv in c.symbols) using(var src=read(root+"/input/"+kv.Value.source+".dwg"))
     prototypes.Add(kv.Key,imp(d,src,kv.Value.handle));
 var produced=new List<string>();
 using(var t=d.TransactionManager.StartTransaction()){
 var ms=(BlockTableRecord)t.GetObject(model(d),OpenMode.ForWrite);
 var imported=ms.Cast<ObjectId>().Where(id=>!before.Contains(id)).ToArray(); foreach(var o in c.ops){try{
 var e=clone(t,ms,(Entity)t.GetObject(prototypes[o.h],OpenMode.ForRead));
 produced.Add(e.Handle.ToString());
 if(!String.IsNullOrEmpty(o.layer)){
 var layers=(LayerTable)t.GetObject(d.LayerTableId,OpenMode.ForRead);
 if(!layers.Has(o.layer)){
 var src=(LayerTableRecord)t.GetObject(e.LayerId,OpenMode.ForRead);
 var layer=new LayerTableRecord(){Name=o.layer,Color=src.Color,LineWeight=src.LineWeight,LinetypeObjectId=src.LinetypeObjectId};
 layers.UpgradeOpen();layers.Add(layer);t.AddNewlyCreatedDBObject(layer,true);
 }}
 var type=e.GetRXClass().DxfName;
 if((o.t=="p" || (o.t=="s" && o.dn>0)) && type!="TCH_PIPE") throw new InvalidDataException("Expected native pipe: "+o.h);
 if(o.t=="title" && type!="TCH_DRAWINGNAME") throw new InvalidDataException("Expected native drawing title"); if(o.t=="l" && type!="TCH_MULTILEADER") throw new InvalidDataException("Expected native leader");
 if(o.t=="d" && type!="TCH_DIMENSION2") throw new InvalidDataException("Expected native dimension");
 var a=new Point3d(o.a[0],o.a[1],0);if(o.t=="p"){var gp=Grips(e);var p=new Point3d(a.X,a.Y,gp[0].Z);var end=new Point3d(o.b[0],o.b[1],gp[1].Z);Start(e.UnmanagedObject,ref p,0,0);End(e.UnmanagedObject,ref end,0,0);Diameter(e.UnmanagedObject,o.dn);Prefix(e.UnmanagedObject,"DN");var mid=p+(end-p)*.5+(Math.Abs(p.X-end.X)>Math.Abs(p.Y-end.Y)?new Vector3d(0,150,0):new Vector3d(-160,0,0));if(o.label!=null)mid=new Point3d(o.label[0],o.label[1],mid.Z);LabelLoc(e.UnmanagedObject,ref mid);PipeTextHeight(e.UnmanagedObject,2.4);DrawLabel(e.UnmanagedObject,o.show?1:0);}
else if(o.t=="s"){var br=e as BlockReference;var p=br==null?Grips(e)[o.idx]:br.Position;if(o.rot!=0)e.TransformBy(Matrix3d.Rotation(o.rot,Vector3d.ZAxis,p));move(e,a.X-p.X,a.Y-p.Y);if(!String.IsNullOrEmpty(o.layer))e.Layer=o.layer;else if(o.h=="SIDE_LEFT"||o.h=="SIDE_RIGHT")e.Layer="EQUIP_雨水";if(o.dn>0){Diameter(e.UnmanagedObject,o.dn);DrawLabel(e.UnmanagedObject,0);}if(type=="TCH_WELL"){WellName(e.UnmanagedObject,o.txt);var wlpt=o.label==null?new Point3d(a.X-1950,a.Y-300,0):new Point3d(o.label[0],o.label[1],0);WellLabel(e.UnmanagedObject,ref wlpt);}else if(o.txt!=null){if(e.GetRXClass().DxfName=="TCH_ELEVATION")SetE(e.UnmanagedObject,o.txt);else if(type=="TCH_ARROW")SetA(e.UnmanagedObject,o.txt);else throw new InvalidDataException("Expected elevation or arrow");}}
else if(o.t=="line"){var ln=(Line)e;ln.StartPoint=a;ln.EndPoint=new Point3d(o.b[0],o.b[1],0);}
else if(o.t=="d"){var g=Grips(e);move(e,a.X-g[2].X,a.Y-g[2].Y);g=Grips(e);e.MoveGripPointsAt(new IntegerCollection(new[]{3}),new Vector3d(o.b[0]-g[3].X,o.b[1]-g[3].Y,0));g=Grips(e);e.MoveGripPointsAt(new IntegerCollection(new[]{0}),new Vector3d(a.X-450-g[0].X,0,0));e.Layer=o.layer;}else if(o.t=="n"){SetTxt(e,o.txt);var b=e.GeometricExtents;move(e,a.X-b.MinPoint.X,a.Y-b.MinPoint.Y);}
else if(o.t=="l"){var gp=Grips(e);move(e,o.b[0]-gp[0].X,o.b[1]-gp[0].Y);var tip=Grips(e)[2];e.MoveGripPointsAt(new IntegerCollection(new[]{2}),new Vector3d(a.X-tip.X,a.Y-tip.Y,0));L1(e.UnmanagedObject,o.txt);L2(e.UnmanagedObject,o.txt2??"");e.RecordGraphicsModified(true);var tb=TextBox(e);var lg=Grips(e);double width=tb.MaxPoint.X-tb.MinPoint.X+200;double sign=lg[1].X<lg[0].X?-1:1;e.MoveGripPointsAt(new IntegerCollection(new[]{1}),new Vector3d(lg[0].X+sign*width-lg[1].X,lg[0].Y-lg[1].Y,0));e.RecordGraphicsModified(true);tb=TextBox(e);double edge=o.b[0]+(o.left?-100:100);double dx=edge-(o.left?tb.MaxPoint.X:tb.MinPoint.X);lg=Grips(e);e.MoveGripPointsAt(new IntegerCollection(Enumerable.Range(3,lg.Count-3).ToArray()),new Vector3d(dx,0,0));PageWidth(e.UnmanagedObject,width+200,0);lg=Grips(e);e.MoveGripPointsAt(new IntegerCollection(new[]{2}),new Vector3d(a.X-lg[2].X,a.Y-lg[2].Y,0));e.Layer=o.layer;}else if(o.t=="title") {SetTitle(e,o.txt);var bb=e.GeometricExtents;move(e,a.X-bb.MinPoint.X,a.Y-bb.MinPoint.Y);}else throw new InvalidDataException("Unknown operation "+o.t);e.RecordGraphicsModified(true);}catch(System.Exception ex){throw new InvalidDataException(o.t+" "+o.h+" "+o.txt,ex);}}
foreach(var id in imported)if(!id.IsErased)t.GetObject(id,OpenMode.ForWrite).Erase();
 t.Commit();}
 File.WriteAllText(outp+"handles.json",js.Serialize(produced));
}
static void Layouts(Database d){var lm=LayoutManager.Current;var frames=cfg.frames;var old=new List<string>();using(var t=d.TransactionManager.StartTransaction()){var dict=(DBDictionary)t.GetObject(d.LayoutDictionaryId,OpenMode.ForRead);foreach(DBDictionaryEntry x in dict)if(!((Layout)t.GetObject(x.Value,OpenMode.ForRead)).ModelType)old.Add(x.Key);}
foreach(var f in frames){ObjectId id=lm.CreateLayout(f.name);lm.CurrentLayout=f.name;DrawingProfile.Apply();using(var t=d.TransactionManager.StartTransaction()){var l=(Layout)t.GetObject(id,OpenMode.ForWrite);var pv=PlotSettingsValidator.Current;pv.SetPlotConfigurationName(l,"DWG To PDF.pc3","ISO_full_bleed_A3_(420.00_x_297.00_MM)");pv.RefreshLists(l);pv.SetPlotPaperUnits(l,PlotPaperUnit.Millimeters);pv.SetPlotRotation(l,PlotRotation.Degrees000);pv.SetPlotType(l,Autodesk.AutoCAD.DatabaseServices.PlotType.Layout);pv.SetUseStandardScale(l,true);pv.SetStdScaleType(l,StdScaleType.StdScale1To1);pv.SetCurrentStyleSheet(l,"monochrome.ctb");l.PlotPlotStyles=true;var b=(BlockTableRecord)t.GetObject(l.BlockTableRecordId,OpenMode.ForWrite);foreach(ObjectId i in b){var q=t.GetObject(i,OpenMode.ForRead) as Viewport;if(q!=null&&q.Number!=1){q.UpgradeOpen();q.Erase();}}var vp=new Viewport();b.AppendEntity(vp);t.AddNewlyCreatedDBObject(vp,true);vp.CenterPoint=new Point3d(210,148.5,0);vp.Width=420;vp.Height=297;vp.ViewDirection=Vector3d.ZAxis;vp.ViewCenter=new Point2d((f.b[0]+f.b[2])/2,(f.b[1]+f.b[3])/2);vp.ViewHeight=297*f.scale;vp.CustomScale=1/f.scale;vp.On=true;vp.Locked=true;vp.Layer="Defpoints";t.Commit();}}
foreach(var n in old)lm.DeleteLayout(n);lm.CurrentLayout=frames[0].name;}
[CommandMethod("VDIMS")] public static void Dimensions(){
 var doc=Application.DocumentManager.MdiActiveDocument;
 try{
 foreach(var chain in cfg.dimensions){
 var ids=new HashSet<ObjectId>();
 using(var t=doc.Database.TransactionManager.StartTransaction()) foreach(ObjectId id in (BlockTableRecord)t.GetObject(model(doc.Database),OpenMode.ForRead))ids.Add(id);
 var pts=chain.levels.Select(y=>new Point3d(chain.x,y,0)).ToList();
 var args=new List<object>{"TDimMP",pts[0],pts[1],new Point3d(chain.labelX,(pts[0].Y+pts[1].Y)/2,0)};
 args.AddRange(pts.Skip(2).Cast<object>()); args.Add("");
 Application.SetSystemVariable("OSMODE",0);doc.Editor.Command(args.ToArray());
 using(var t=doc.Database.TransactionManager.StartTransaction()){
 var added=((BlockTableRecord)t.GetObject(model(doc.Database),OpenMode.ForRead)).Cast<ObjectId>().Where(id=>!ids.Contains(id)).Select(id=>(Entity)t.GetObject(id,OpenMode.ForRead));
 if(!added.Any(e=>e.GetRXClass().DxfName=="TCH_DIMENSION2" && chain.levels.All(y=>Grips(e).Cast<Point3d>().Any(pt=>Math.Abs(pt.Y-y)<.02))))throw new InvalidDataException("Native floor dimension chain failed");
 }}
 doc.SendStringToExecute("V4SAVE\n",true,false,false);
 }catch(System.Exception ex){log(ex.ToString());doc.SendStringToExecute("CADPOOLFAIL\n",true,false,false);}
}
[CommandMethod("V4SAVE",CommandFlags.Session)]public static void Save(){try{var doc=Application.DocumentManager.MdiActiveDocument;using(doc.LockDocument()){Layouts(doc.Database);DrawingProfile.Apply();doc.Database.SaveAs(outp+"drawing.dwg",DwgVersion.AC1032);}log("saved "+DateTimeOffset.Now);doc.CloseAndDiscard();Review.Go();}catch(System.Exception e){log(e.ToString());Application.DocumentManager.MdiActiveDocument.SendStringToExecute("CADPOOLFAIL\n",true,false,false);}}
[CommandMethod("ZBUILD",CommandFlags.Session)]public static void Run(){try{var dm=Application.DocumentManager;var working=root+"/work/start.dwg";using(var blank=new Database(true,true)){blank.SaveAs(working,DwgVersion.AC1032);}var doc=dm.Open(working,false);dm.MdiActiveDocument=doc;using(doc.LockDocument()){Application.SetSystemVariable("LAYOUTREGENCTL",0);LayoutManager.Current.CurrentLayout="Model";DrawingProfile.Apply();Build(doc.Database);}doc.SendStringToExecute("VDIMS\n",true,false,false);}catch(System.Exception e){log(e.ToString());Application.DocumentManager.MdiActiveDocument.SendStringToExecute("CADPOOLFAIL\n",true,false,false);}}
}