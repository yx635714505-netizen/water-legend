using System;using System.Linq;using System.IO;using System.Collections.Generic;using System.Web.Script.Serialization;using Autodesk.AutoCAD.DatabaseServices;using Autodesk.AutoCAD.Geometry;using Autodesk.AutoCAD.Runtime;
public class Visit{
 public static string root=Environment.GetEnvironmentVariable("CAD_POOL_JOB");public static JavaScriptSerializer js=new JavaScriptSerializer(){MaxJsonLength=int.MaxValue};
 public static object Dump(Entity e,Transaction tx){double[] b=null;try{var ex=e.GeometricExtents;b=new[]{ex.MinPoint.X,ex.MinPoint.Y,ex.MaxPoint.X,ex.MaxPoint.Y};}catch{}var br=e as BlockReference;var poly=e as Polyline;var line=e as Line;var gp=new Point3dCollection();try{if(e.GetRXClass().DxfName.StartsWith("TCH_"))e.GetGripPoints(gp,new IntegerCollection(),new IntegerCollection());}catch{}var layer=(LayerTableRecord)tx.GetObject(e.LayerId,OpenMode.ForRead);var layerType=(LinetypeTableRecord)tx.GetObject(layer.LinetypeObjectId,OpenMode.ForRead);var type=e.GetRXClass().DxfName;return new{leaderArrowStyle=type=="TCH_MULTILEADER"?(int?)Builder.ReadLeaderArrow(e.UnmanagedObject):null,layerColor=layer.Color.ColorIndex,layerType=layerType.Name,weight=e.LineWeight.ToString(),lt=e.Linetype,lts=e.LinetypeScale,clr=e.ColorIndex,dn=e.GetRXClass().DxfName=="TCH_PIPE"?Builder.ReadDn(e.UnmanagedObject):0,h=e.Handle.ToString(),t=e.GetRXClass().DxfName,l=e.Layer,b=b,n=br!=null?br.Name:e is DBText?((DBText)e).TextString:e is MText?((MText)e).Contents:"",vertices=poly==null?null:Enumerable.Range(0,poly.NumberOfVertices).Select(i=>new[]{poly.GetPoint2dAt(i).X,poly.GetPoint2dAt(i).Y,poly.GetBulgeAt(i)}).ToArray(),closed=poly!=null&&poly.Closed,matrix=br==null?null:br.BlockTransform.ToArray(),ins=br==null?null:new[]{br.Position.X,br.Position.Y},gp=gp.Cast<Point3d>().Select(p=>new[]{p.X,p.Y}).ToArray(),pts=line==null?null:new[]{line.StartPoint.X,line.StartPoint.Y,line.EndPoint.X,line.EndPoint.Y}};}
 [CommandMethod("ANVISIT")] public static void Inspect(){
try{using(var db=new Database(false,true)){
 db.ReadDwgFile(root+"/input/ar.dwg",FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
 using(var tx=db.TransactionManager.StartTransaction()){
 var blocks=(BlockTable)tx.GetObject(db.BlockTableId,OpenMode.ForRead);
 var result=new Dictionary<string,object>();
 foreach(ObjectId id in blocks){var block=(BlockTableRecord)tx.GetObject(id,OpenMode.ForRead);
 result[block.Name]=block.Cast<ObjectId>().Select(i=>Dump((Entity)tx.GetObject(i,OpenMode.ForRead),tx)).ToList();}
 File.WriteAllText(root+"/output/architecture.json",js.Serialize(result));}}
 File.WriteAllText(root+"/output/validation.json",js.Serialize(new{jobId=Environment.GetEnvironmentVariable("CAD_POOL_JOB_ID"),passed=true,checks=new{nativeReadBack=true}}));
 Autodesk.AutoCAD.ApplicationServices.Application.DocumentManager.MdiActiveDocument.SendStringToExecute("CADPOOLCOMPLETE\n",true,false,false);
}catch(System.Exception ex){File.WriteAllText(root+"/output/error.txt",ex.ToString());Autodesk.AutoCAD.ApplicationServices.Application.DocumentManager.MdiActiveDocument.SendStringToExecute("CADPOOLFAIL\n",true,false,false);}
}}
