using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Security.Cryptography;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

// Capture IDs while the WblockCloneObjects map still exists. Store them on the
// inserted reference so a reopened drawing identifies the actual column and wall instances.
public static class JointEvidence {
    const string Key = "WATER_JOINT_SOURCES";
    public class Request { public string @base, source, columnBlock, hatch; public Wall[] walls; }
    public class Wall { public string sourceWall; }
    public class Riser { public Request embeddedWallEvidence; }
    public class Plan { public Riser[] risers; }
    public class Config { public Plan[] riserPlans; }
    public class Proof {
        public string @base, source, sourceSha256, importedSource, importedSha256, columnBlock, hatch, columnPath;
        public double[][] outline, importedOutline;
        public Dictionary<string,string> wallPaths;
    }

    static string Input(string name) {
        if (String.IsNullOrEmpty(name) || !System.Text.RegularExpressions.Regex.IsMatch(name, @"^[a-z][a-z0-9_-]*$"))
            throw new InvalidDataException("无效的建筑底图来源");
        return Path.Combine(Visit.root,"input",name+".dwg");
    }
    static string Hash(string name) {
        using (var file = File.OpenRead(Input(name)))
        using (var hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(file)).Replace("-","").ToLowerInvariant();
    }
    static ObjectId Id(Database db, string handle) {
        return db.GetObjectId(false,new Handle(Convert.ToInt64(handle,16)),0);
    }
    static double[][] HatchOutline(Database db, Request request, Matrix3d placement) {
        using (var tx = db.TransactionManager.StartOpenCloseTransaction()) {
            var column = tx.GetObject(Id(db,request.columnBlock), OpenMode.ForRead) as BlockReference;
            var hatch = tx.GetObject(Id(db,request.hatch), OpenMode.ForRead) as Hatch;
            if (column == null || hatch == null || hatch.OwnerId != column.BlockTableRecord ||
                column.OwnerId != SymbolUtilityServices.GetBlockModelSpaceId(db) || hatch.NumberOfLoops != 1)
                throw new InvalidDataException("填充不属于所选原图柱实例或不是单环 " + request.hatch);
            var loop = hatch.GetLoopAt(0);
            var vertices = new List<Point2d>();
            if (loop.IsPolyline) {
                foreach (BulgeVertex v in loop.Polyline) {
                    if (v.Bulge != 0) throw new InvalidDataException("柱面含弧段 " + request.hatch);
                    vertices.Add(v.Vertex);
                }
            } else {
                var edges = loop.Curves.Cast<Curve2d>().Select(c => c as LineSegment2d).ToArray();
                for (int i=0; i<edges.Length; i++) {
                    var previous = edges[(i+edges.Length-1)%edges.Length];
                    if (edges[i] == null || previous == null || previous.EndPoint.GetDistanceTo(edges[i].StartPoint) > .001)
                        throw new InvalidDataException("柱面边界不是连续直线环 " + request.hatch);
                    vertices.Add(edges[i].StartPoint);
                }
            }
            if (vertices.Count > 1 && vertices[0].GetDistanceTo(vertices.Last()) < .000001)
                vertices.RemoveAt(vertices.Count-1);
            if (vertices.Count < 3) throw new InvalidDataException("柱面顶点不足 " + request.hatch);
            var transform = placement * column.BlockTransform * Matrix3d.PlaneToWorld(hatch.Normal);
            return vertices.Select(v => new Point3d(v.X,v.Y,hatch.Elevation).TransformBy(transform))
                           .Select(p => new[]{p.X,p.Y}).ToArray();
        }
    }
    public static void Capture(Builder.Base b, Database imported, IdMapping map, BlockReference root,
                               Transaction tx, IEnumerable<Request> requests) {
        var proofs = new List<Proof>();
        var importedHash = Hash(b.source);
        foreach (var group in requests.GroupBy(e => new {e.source,e.columnBlock,e.hatch})) {
            var e = group.First();
            if (e.source != "ar") throw new InvalidDataException("墙柱交接证据须追溯至建筑原图 ar");
            if (!b.ids.Contains(e.columnBlock)) throw new InvalidDataException("所选柱不在导入清单中");
            var polygon = HatchOutline(imported,e,root.BlockTransform);
            var originalPolygon = polygon;
            var originalHash = importedHash;
            if (b.source != "ar") {
                // A classified copy may have added outlines. Both drawings must
                // independently contain the claimed hatch on this column instance.
                using (var original = new Database(false,true)) {
                    original.ReadDwgFile(Input("ar"),FileOpenMode.OpenForReadAndAllShare,true,null);
                    original.CloseInput(true);
                    originalPolygon = HatchOutline(original,e,root.BlockTransform);
                }
                originalHash = Hash("ar");
            }
            var wallPaths = new Dictionary<string,string>();
            foreach (string wall in group.SelectMany(r => r.walls).Select(w => w.sourceWall).Distinct()) {
                if (!b.ids.Contains(wall)) throw new InvalidDataException("所选墙不在导入清单中");
                wallPaths.Add(wall,map[Id(imported,wall)].Value.Handle.ToString());
            }
            proofs.Add(new Proof { @base=b.name, source=e.source, sourceSha256=originalHash,
                importedSource=b.source, importedSha256=importedHash, columnBlock=e.columnBlock, hatch=e.hatch,
                columnPath=map[Id(imported,e.columnBlock)].Value.Handle.ToString(), outline=originalPolygon,
                importedOutline=polygon, wallPaths=wallPaths });
        }
        root.CreateExtensionDictionary();
        var dict = (DBDictionary)tx.GetObject(root.ExtensionDictionary,OpenMode.ForWrite);
        var record = new Xrecord();
        var json = Visit.js.Serialize(proofs);
        var chunks = new List<TypedValue>();
        for (int i=0; i<json.Length; i+=100)
            chunks.Add(new TypedValue((int)DxfCode.Text,json.Substring(i,Math.Min(100,json.Length-i))));
        record.Data = new ResultBuffer(chunks.ToArray());
        dict.SetAt(Key,record);
        tx.AddNewlyCreatedDBObject(record,true);
    }

    public static IEnumerable<Proof> Read(BlockTableRecord model, Transaction tx) {
        foreach (ObjectId id in model) {
            var root = tx.GetObject(id,OpenMode.ForRead) as BlockReference;
            if (root == null || root.ExtensionDictionary.IsNull) continue;
            var dict = (DBDictionary)tx.GetObject(root.ExtensionDictionary,OpenMode.ForRead);
            if (!dict.Contains(Key)) continue;
            var record = (Xrecord)tx.GetObject(dict.GetAt(Key),OpenMode.ForRead);
            var json = String.Concat(record.Data.AsArray().Select(v => (string)v.Value));
            foreach (var proof in Visit.js.Deserialize<Proof[]>(json)) {
                if (proof.@base != root.Name) throw new InvalidDataException("底图实例名称已改变");
                string prefix = root.Handle.ToString()+"/";
                proof.columnPath = prefix+proof.columnPath;
                proof.wallPaths = proof.wallPaths.ToDictionary(x=>x.Key,x=>prefix+x.Value);
                yield return proof;
            }
        }
    }
}
