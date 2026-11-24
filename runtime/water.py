"""Prepare native CAD jobs and verify reopened DWG objects. Python 3.8+."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
PIPES = dict(zip(
    "JPLAN JSYS WPLAN WSYS FPLAN FSYS YPLAN YSYS JDOT WDOT YDOT FDOT".split(),
    "84101 85A47 85267 85BC5 85B92 85A81 85344 85C53 8411B 84144 85287 84DD2".split()))
MODULES = "tch_initstart tch_kernal tch_utility tch_pipebase tch_pipewire tch_annotate".split()


def load(path):
    return json.loads(path.read_text("utf-8-sig"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def require(test, message):
    if not test:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(args):
    target = args.package.resolve()
    sources = {}
    if args.inspect:
        sources["ar"] = args.input.resolve()
    else:
        spec = load(args.input)
        for name, entry in spec.get("sources", {}).items():
            require(re.fullmatch(r"[a-z][a-z0-9_-]*", name) and name not in ("style","side","pot"), name)
            source = (args.input.resolve().parent / entry["path"]).resolve()
            require(digest(source) == entry["sha256"].lower(), "Source changed: " + name)
            sources[name] = source
        sources.update(style=ASSETS/"pipe-style/水施线形参照.dwg",
                       side=ASSETS/"pipe-style/露台墙侧排口.dwg",
                       pot=ASSETS/"sources/03-蛇形山扶洲周府-水施_t8.dwg")
        spec.setdefault("symbols", {}).update(SIDE_LEFT=dict(source="side", handle="79"),
            SIDE_RIGHT=dict(source="side", handle="83"), CLEAN=dict(source="pot",handle="20A8"),
            WELL=dict(source="pot",handle="208B"), POT=dict(source="pot",handle="2072"))
        for item in list(spec["symbols"].values()) + spec["bases"]:
            require(item["source"] in sources, "Unknown DWG source")
        frames = spec["frames"]
        require(frames and len({f["name"] for f in frames}) == len(frames), "Unique layouts required")
        for f in frames:
            x,y,r,t = f["b"]
            require(f["scale"] > 0 and abs(r-x-420*f["scale"]) < .1 and
                    abs(t-y-297*f["scale"]) < .1, "A3 bounds and scale: "+f["name"])
        for op in spec["ops"]:
            require(op["t"] in ("p","s","l","d","n","line","title"), "Unknown operation")
            require(op["h"] in set(PIPES) | {"BOWL"} | spec["symbols"].keys(), "Unknown sample")
            if op["t"] == "p":
                require(op["h"] in PIPES and op["dn"] > 0 and op["a"] != op["b"], "Pipe geometry")
        for chain in spec["dimensions"]:
            require(len(chain["levels"]) >= 2 and chain["levels"] == sorted(set(chain["levels"])), "Floor levels")
    acad, tangent = args.acad.resolve(), args.tangent.resolve()
    require(all((tangent/(m+".arx")).is_file() for m in MODULES), "Check Tianzheng module directory")
    compiler = Path(os.environ["SystemRoot"])/"Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    target.mkdir(parents=True, exist_ok=False)
    scripts = target/"scripts"
    scripts.mkdir()
    inputs = target/"input"
    inputs.mkdir()
    for name, source in sources.items():
        shutil.copyfile(source, inputs/(name+".dwg"))
    subprocess.run([str(compiler), "/nologo", "/target:library","/platform:x64",
        "/r:System.Web.Extensions.dll", *["/r:"+str(acad/(lib+".dll")) for lib in ("acmgd","acdbmgd","accoremgd")],
        "/out:"+str(scripts/"Engine.dll"), *map(str,sorted((HERE/"native").glob("*.cs")))], check=True)
    commands = [f'(arxload "{(tangent/(m+".arx")).as_posix()}")' for m in MODULES]
    commands += ['(command "_.NETLOAD" (strcat (getenv "CAD_POOL_JOB") "/scripts/Engine.dll"))',
                 "ANVISIT" if args.inspect else "ZBUILD"]
    (scripts/"command.scr").write_bytes(("\r\n".join(commands)+"\r\n").encode("gbk"))
    expected = ["architecture.json"] if args.inspect else ["drawing.dwg","aud.json","handles.json"] + [
        f"page{i}.pdf" for i in range(len(spec["frames"]))]
    if not args.inspect:
        save(scripts/"cfg.json", spec)
    save(target/"job.json", dict(isolationContract=1,validationReport="output/validation.json",
                                 expectedOutputs=["output/"+n for n in expected]))


def point(p):
    return tuple(round(v, 2) for v in p[:2])


def verify(job):
    out = job/"output"
    cfg = load(job/"scripts/cfg.json")
    report = load(out/"validation.json")
    completion = load(job/"control/result.json")
    exit_info = load(job/"control/exit.json")
    require(completion["success"] and completion["jobId"] == report["jobId"] and
            exit_info["exitCode"] == 0 and not exit_info["terminated"], "CAD job did not finish cleanly")
    require(report["passed"] and report["jobId"] == load(job/"job.json")["jobId"] and
            report["checks"]["nativeReadBack"] and report["checks"]["layoutsPrinted"] == len(cfg["frames"]), "Invalid CAD report")
    for i in range(len(cfg["frames"])):
        require((out/f"page{i}.pdf").read_bytes().startswith(b"%PDF-"), f"Missing PDF {i}")
    handles = load(out/"handles.json")
    rows = {e["h"]: e for e in load(out/"aud.json")}
    require(len(set(handles)) == len(handles) == len(cfg["ops"]), "Incomplete CAD operations")
    profiles = load(ASSETS/"pipe-style/管道线型索引.json")["object_profiles"]
    native = {h:p for p in profiles for h in p["handles"]}
    networks = {}
    for index, (h, op) in enumerate(zip(handles,cfg["ops"])):
        e = rows[h]
        require(e["b"] is not None, f"Missing native extents at operation {index}")
        if op["h"] in ("SIDE_LEFT", "SIDE_RIGHT"):
            require(e["t"] == "TCH_EQUIPMENT" and e["l"] == op.get("layer","EQUIP_雨水")
                    and point(e["gp"][0]) == point(op["a"]), "Side outlet "+h)
        if op["h"] in PIPES:
            expected = native[PIPES[op["h"]]]
            require(e["t"] == "TCH_PIPE" and e["l"] == expected["layer"] and
                    e["lt"].lower() == expected["linetype"].lower() and e["clr"] == 256 and
                    abs(e["lts"]-float(expected["scale"])) < .001 and e["dn"] == op["dn"], "Pipe style "+h)
            a = point(op["a"])
            require(point(e["gp"][0]) == a, "Start "+h)
            if op["t"] == "p":
                b = point(e["gp"][1])
                require(b == point(op["b"]), "End "+h)
                if op.get("network"):
                    graph = networks.setdefault(op["network"],{})
                    graph.setdefault(a,set()).add(b)
                    graph.setdefault(b,set()).add(a)
        elif op["t"] == "l":
            require(e["t"]=="TCH_MULTILEADER" and point(op["a"])==point(e["gp"][2]), "Leader "+h)
        elif op["t"] == "d":
            require(e["t"]=="TCH_DIMENSION2" and point(op["b"])==point(e["gp"][3]), "Dimension "+h)
    for check in cfg.get("connections",[]):
        graph=networks[check["network"]]
        pending=[point(check["from"])]
        visited=set()
        while pending:
            pt=pending.pop()
            if pt not in visited:
                visited.add(pt)
                pending.extend(graph[pt]-visited)
        require(all(point(end) in visited for end in check["to"]), "Disconnected "+check["network"])
    named = {}
    for h, op in zip(handles, cfg["ops"]):
        if "id" in op:
            require(op["id"] not in named, "Duplicate ID "+op["id"])
            named[op["id"]] = rows[h]
    used = set()
    for service in cfg.get("services", []):
        for view in ("plan", "system"):
            key = service[view]
            require(key not in used, "Repeated service endpoint "+key)
            used.add(key)
            actual = named[key]
            require(point(service[view+"Point"]) == point(actual["gp"][service.get(view+"Grip",0)]),
                    "Wrong service endpoint "+key)
    for check in cfg.get("clearances", []):
        x1,y1,x2,y2 = named[check["id"]]["b"]
        margin = check["margin"]
        require(margin >= 0, "Negative clearance")
        for left,bottom,right,top in check["obstacles"]:
            require(x2+margin <= left or x1-margin >= right or y2+margin <= bottom or y1-margin >= top,
                    "Insufficient clearance "+check["id"])
    print(f'{len(cfg["frames"])} layouts, {len(handles)} native operations verified.')


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_subparsers(dest="mode", required=True)
    prep=modes.add_parser("prepare")
    prep.add_argument("input", type=Path)
    prep.add_argument("package", type=Path)
    prep.add_argument("--inspect",action="store_true")
    prep.add_argument("--acad",type=Path,default="C:/Program Files/Autodesk/AutoCAD 2020")
    prep.add_argument("--tangent",type=Path,default="C:/Tangent/TArchT20V8/sys23x64")
    check=modes.add_parser("verify")
    check.add_argument("job",type=Path)
    args=parser.parse_args()
    if args.mode=="prepare":
        prepare(args)
    else:
        verify(args.job)
