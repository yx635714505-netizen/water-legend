using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
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

    public static string DrawingHash()
    {
        using (var file = new FileStream(Path.Combine(Root, "output", "drawing.dwg"),
                   FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
    }
}
