using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

public static class RiserReadback {
    static readonly StringComparer IgnoreCase = StringComparer.OrdinalIgnoreCase;

    static readonly string[] SewageLayers = {"PIPE-污水","S-PIPE-污水"};

    static double[] XY(Point3d p) { return new[]{p.X, p.Y}; }
    static string Plain(string layer) { return layer.Split('$').Last(); }
    const string RetainedLayer = "WATER_ORIGINAL_BARRIER_LAYER";

    // The plotting routine puts architectural terrace column outlines on layer 0.
    public static void RememberLayer(Entity entity, Transaction tx) {
        if (!Plain(entity.Layer).Equals("A-立面看线",StringComparison.OrdinalIgnoreCase)) return;
        if(entity.ExtensionDictionary.IsNull) entity.CreateExtensionDictionary();
        var dict=(DBDictionary)tx.GetObject(entity.ExtensionDictionary,OpenMode.ForWrite);
        if(dict.Contains(RetainedLayer)) return;
        var record=new Xrecord();
        record.Data=new ResultBuffer(new TypedValue((int)DxfCode.Text,Plain(entity.Layer)));
        dict.SetAt(RetainedLayer,record);
        tx.AddNewlyCreatedDBObject(record,true);
    }

    static string AuditLayer(Entity entity, Transaction tx) {
        if(!entity.ExtensionDictionary.IsNull) {
            var dict=(DBDictionary)tx.GetObject(entity.ExtensionDictionary,OpenMode.ForRead);
            if(dict.Contains(RetainedLayer)) {
                var rec=(Xrecord)tx.GetObject(dict.GetAt(RetainedLayer),OpenMode.ForRead);
                return (string)rec.Data.AsArray()[0].Value;
            }
        }
        return Plain(entity.Layer);
    }

    // Walls of unknown section use a containing envelope. It may reject a tight
    // placement but must never certify an embedded pipe on that basis.
    static Point3d[] Envelope(Entity entity) {
        var e = entity.GeometricExtents;
        return new[]{e.MinPoint, new Point3d(e.MaxPoint.X,e.MinPoint.Y,0),
                     e.MaxPoint, new Point3d(e.MinPoint.X,e.MaxPoint.Y,0)};
    }

    static int OutlineVertices(Polyline p) {
        if(p==null || p.NumberOfVertices<3) return 0;
        int n=p.NumberOfVertices;
        bool same=p.GetPoint3dAt(0).DistanceTo(p.GetPoint3dAt(n-1))<=1e-6;
        if(!p.Closed && !same) return 0;
        int count=same?n-1:n;
        if(count<3 || Enumerable.Range(0,count).Any(i=>p.GetBulgeAt(i)!=0 ||
            p.GetStartWidthAt(i)!=0 || p.GetEndWidthAt(i)!=0)) return 0;
        return Math.Abs(p.Area)>1e-6 ? count : 0;
    }

    static Point3d[] Footprint(Entity entity, out bool exact) {
        exact = false;
        var poly = entity as Polyline;
        int count=OutlineVertices(poly);
        if (count>0) {
            exact=true;
            return Enumerable.Range(0,count).Select(poly.GetPoint3dAt).ToArray();
        }
        if (entity.GetRXClass().DxfName=="TCH_COLUMN") {
            var points = new Point3dCollection();
            entity.GetGripPoints(points,new IntegerCollection(),new IntegerCollection());
            var box=Envelope(entity);
            if (points.Count==9 && Enumerable.Range(0,4).All(i=>box[i].DistanceTo(new Point3d(points[i+1].X,points[i+1].Y,box[i].Z))<0.01)) {
                exact=true;
                return box;
            }
        }
        return Envelope(entity);
    }

    static void Walk(BlockTableRecord block, Transaction tx, Matrix3d transform, string prefix,
                     string inherited, HashSet<ObjectId> active, HashSet<string> extra, List<object> objects,
                     List<object> sewage, List<object> rain) {
        if (!active.Add(block.ObjectId)) throw new InvalidDataException("循环引用块 "+prefix);
        if (block.IsFromExternalReference && block.XrefStatus!=XrefStatus.Resolved)
            throw new InvalidDataException("建筑外参未解析 "+block.Name);
        foreach(ObjectId id in block) {
            var entity=tx.GetObject(id,OpenMode.ForRead) as Entity;
            if(entity==null) continue;
            string path=prefix+entity.Handle.ToString(), type=entity.GetRXClass().DxfName;
            string layer=AuditLayer(entity,tx);
            if (layer=="0") layer=inherited;
            var br=entity as BlockReference;
            if (br!=null) {
                if (br is MInsertBlock) throw new InvalidDataException("需展开阵列引用的实例坐标 "+path);
                Walk((BlockTableRecord)tx.GetObject(br.BlockTableRecord,OpenMode.ForRead),tx,
                     transform*br.BlockTransform,path+"/",layer,active,extra,objects,sewage,rain);
                continue;
            }
            bool verticalLayer=layer.StartsWith("VPIPE",StringComparison.OrdinalIgnoreCase);
            if (type=="TCH_PIPE") {
                var grips=new Point3dCollection();
                entity.GetGripPoints(grips,new IntegerCollection(),new IntegerCollection());
                if (SewageLayers.Contains(layer,IgnoreCase) && grips.Count>=2) {
                    sewage.Add(new {path, a=XY(grips[0].TransformBy(transform)),
                        b=XY(grips[1].TransformBy(transform)), dn=Builder.ReadDn(entity.UnmanagedObject)});
                }
                if ((IgnoreCase.Equals(layer,"PIPE-雨水") || IgnoreCase.Equals(layer,"S-PIPE-雨水")) && grips.Count>=2)
                    rain.Add(new {path, a=XY(grips[0].TransformBy(transform)), b=XY(grips[1].TransformBy(transform))});
                if (!verticalLayer && grips.Count!=1) continue;
                if (grips.Count!=1) throw new InvalidDataException("立管夹点无法确定 "+path);
                objects.Add(new {kind="riser",path,layer,at=XY(grips[0].TransformBy(transform)),dn=Builder.ReadDn(entity.UnmanagedObject)});
                continue;
            }
            if (verticalLayer && type!="TCH_PIPEFITTING")
                throw new InvalidDataException("立管图层含不可识别对象 "+path+" "+type);
            bool native=type=="TCH_WALL" || type=="TCH_COLUMN" || type=="TCH_CURTAIN_WALL";
            // The elevation-detail layer also contains unrelated open furniture and facade lines.
            var outline=entity as Polyline;
            bool terraceOutline=layer=="A-立面看线" && outline!=null && (outline.Closed || OutlineVertices(outline)>0);
            bool barrier=native || extra.Contains(layer) ||
                (entity is Curve || entity is Hatch || entity is Solid) &&
                (layer.IndexOf("WALL",StringComparison.OrdinalIgnoreCase)>=0 ||
                 layer.IndexOf("COLUMN",StringComparison.OrdinalIgnoreCase)>=0 ||
                 layer.Contains("墙体") || layer.Contains("柱") || terraceOutline);
            if(!barrier && type!="ACAD_PROXY_ENTITY") continue;
            bool exact;
            var polygon=Footprint(entity,out exact).Select(p=>XY(p.TransformBy(transform))).ToArray();
            var curve=entity as Curve;
            bool incomplete=type=="ACAD_PROXY_ENTITY" || (curve!=null && !native && !curve.Closed && !exact);
            objects.Add(new {kind=incomplete?"unknown":"barrier",path,layer,type,exact,polygon});
        }
        active.Remove(block.ObjectId);
    }

    public static void Write(Database db, Transaction tx, BlockTableRecord model, string folder) {
        var json=new JavaScriptSerializer {MaxJsonLength=int.MaxValue};
        var config=json.Deserialize<LayerConfig>(File.ReadAllText(Path.Combine(Visit.root,"scripts","cfg.json")));
        var objects=new List<object>();
        var sewage=new List<object>();
        var rain=new List<object>();
        Walk(model,tx,Matrix3d.Identity,"","0",new HashSet<ObjectId>(),
             new HashSet<string>(config.barrierLayers??new string[0],IgnoreCase),objects,sewage,rain);
        File.WriteAllText(Path.Combine(folder,"riser-geometry.json"),
            json.Serialize(new {version=1,jointProofs=JointEvidence.Read(model,tx).ToArray(),dwgSha256=DrawingProfile.DrawingHash(),
                                barrierLayers=config.barrierLayers??new string[0],objects,sewageLayers=SewageLayers,sewage,rain}));
    }
    public class LayerConfig {public string[] barrierLayers;}
}
