using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using System.Web.Script.Serialization;
using Autodesk.AutoCAD.ApplicationServices;

public static class DrawingProfile
{
    static string Root { get { return Environment.GetEnvironmentVariable("CAD_POOL_JOB"); } }
    static Dictionary<string, int> Settings()
    {
        return new JavaScriptSerializer().Deserialize<Dictionary<string, int>>(
            File.ReadAllText(Path.Combine(Root, "scripts", "drawing-profile.json")));
    }

    public static void Apply()
    {
        foreach (var setting in Settings())
            Application.SetSystemVariable(setting.Key, Convert.ChangeType(setting.Value, Application.GetSystemVariable(setting.Key).GetType()));
    }

    public static Dictionary<string, int> Read()
    {
        var actual = new Dictionary<string, int>();
        foreach (var setting in Settings())
            actual[setting.Key] = Convert.ToInt32(Application.GetSystemVariable(setting.Key));
        return actual;
    }

    public static string BaseConfig(Database db, bool checkEmpty)
    {
        using (var t = db.TransactionManager.StartTransaction())
        {
            var dictionary = (DBDictionary)t.GetObject(db.NamedObjectsDictionaryId, OpenMode.ForRead);
            var config = t.GetObject(dictionary.GetAt("TCH_DBPSCONFIG"), OpenMode.ForRead);
            if (config.GetRXClass().DxfName != "TCH_PSCONFIG")
                throw new InvalidDataException("缺少天正原生水施配置");
            if (checkEmpty)
            {
                var model = (BlockTableRecord)t.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                if (model.Cast<ObjectId>().Any())
                    throw new InvalidDataException("通用水施底板模型空间应为空");
            }
            return config.GetRXClass().DxfName;
        }
    }

    public static Dictionary<string, double> SewageWidths(Database db)
    {
        var widths = new Dictionary<string, double>();
        using (var t = db.TransactionManager.StartTransaction())
        {
            var model = (BlockTableRecord)t.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
            foreach (ObjectId id in model)
            {
                var pipe = (Entity)t.GetObject(id, OpenMode.ForRead);
                if (pipe.Layer != "PIPE-污水" || pipe.GetRXClass().DxfName != "TCH_PIPE" ||
                    Builder.ReadDn(pipe.UnmanagedObject) != 200) continue;
                using (var geometry = new DBObjectCollection())
                {
                    try
                    {
                        pipe.Explode(geometry);
                        var strokes = geometry.OfType<Polyline>().Where(p => p.NumberOfVertices >= 2).ToList();
                        widths[pipe.Handle.ToString()] = strokes.Count == 0 ? 0 : strokes[0].GetStartWidthAt(0);
                    }
                    finally { foreach (DBObject part in geometry) part.Dispose(); }
                }
            }
        }
        return widths;
    }

    public static string DrawingHash()
    {
        using (var file = new FileStream(Path.Combine(Root, "output", "drawing.dwg"),
                   FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
    }
}
