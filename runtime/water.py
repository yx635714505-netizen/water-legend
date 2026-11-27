"""Prepare native CAD jobs and verify reopened DWG objects. Python 3.8+."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import riser_audit
import rain_audit
import sewage_audit

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
BASEPLATE = ASSETS / "baseplate/水施通用底板.dwg"
BASEPLATE_SHA256 = "5f2c825ebb9cf977067c2961003426d3a97388528f472e553aefba1ce3cf383f"
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


def production_libraries():
    catalog = load(ASSETS/"legend-catalog.json")
    layout_index = ASSETS/"layout-v2/manifest.json"
    layout = load(layout_index)["native_source"]
    return {"pot": (ASSETS/catalog["source_dwg"], catalog["sha256"]),
            "layout": (layout_index.parent/layout["path"], layout["sha256"])}, catalog["production_symbols"]


def commissioning(cfg):
    example = load(HERE/"commission.json")
    return not cfg.get("bases") and cfg.get("sources") == example["sources"] and all(
        cfg.get(key) == example[key] for key in ("frames", "ops", "dimensions", "connections"))


def check_sheet_numbers(spec):
    names = [frame["name"] for frame in spec["frames"]]
    if commissioning(spec):
        return
    front_index, drawing_index = 0, 1
    seen_system = False
    for name in names:
        if any(word in name for word in ("目录", "说明", "图例")):
            require((front_index > 0) or "目录" in name, "水施-A00 应为目录")
            expected = f"水施-A{front_index:02d}"
            front_index += 1
        else:
            if "平面" in name or any(plan.get("layout") == name for plan in spec.get("riserPlans", [])):
                require(not seen_system, "系统图应接最后一张平面图续号：" + name)
            if "系统" in name:
                seen_system = True
            expected = f"水施-B{drawing_index:02d}"
            drawing_index += 1
        require(re.match(re.escape(expected) + r"(?![\dA-Za-z-])", name),
                f"图别图号应为 {expected}：{name}")


def check_model_arrangement(frames):
    front = [f for f in frames if any(word in f["name"] for word in ("目录", "说明", "图例"))]
    drawings = [f for f in frames if f not in front]
    if not front or not drawings:
        return
    require(frames == front + drawings, "目录和说明页须先于专业图页")
    for column in (front, drawings):
        left = column[0]["b"][0]
        for index, frame in enumerate(column):
            box = frame["b"]
            require(abs(box[0] - left) <= 1, "模型图框应分列左对齐：" + frame["name"])
            if index:
                require(box[3] < column[index-1]["b"][1], "同列图框应按图序向下留缝排列：" + frame["name"])
    require(drawings[0]["b"][0] > max(f["b"][2] for f in front)
            and abs(front[0]["b"][3] - drawings[0]["b"][3]) <= 1,
            "模型空间应左列目录说明、右列平面系统，两列顶边对齐")


def plan_rain_bowls(spec, radius):
    windows = [box for _, box in riser_audit.plan_windows(spec)]
    centres = set()
    for op in spec["ops"]:
        if op["t"] != "s" or op["h"] not in ("BOWL", "BOWL_PLAN"):
            continue
        if any(riser_audit.inside(box, op["a"]) for box in windows):
            if op["h"] == "BOWL":
                op.update(h="BOWL_PLAN", rot=0, idx=0)
            centres.add(tuple(op["a"]))
    # A solid leader dot at the inlet axis obscures the two lines inside the ring.
    for op in spec["ops"]:
        if op["t"] != "l" or op.get("layer") != "DIM_雨水" or tuple(op["a"]) not in centres:
            continue
        x, y = op["a"]
        dx, dy = op["b"][0] - x, op["b"][1] - y
        length = math.hypot(dx, dy)
        if length > radius:
            op["a"] = [x + radius*dx/length, y + radius*dy/length]


def design_sewage_segments(ops):
    return [dict(path=str(i), a=op["a"], b=op["b"], dn=op["dn"])
            for i, op in enumerate(ops) if op["t"] == "p" and op["h"] in ("WPLAN", "WSYS")]


def prepare(args):
    target = args.package.resolve()
    sources = {}
    if args.inspect:
        sources["ar"] = args.input.resolve()
    else:
        spec = load(args.input)
        for name, entry in spec.get("sources", {}).items():
            require(re.fullmatch(r"[a-z][a-z0-9_-]*", name) and name not in ("style","side","pot","layout","baseplate"), name)
            source = (args.input.resolve().parent / entry["path"]).resolve()
            require(digest(source) == entry["sha256"].lower(), "Source changed: " + name)
            sources[name] = source
        require(digest(BASEPLATE) == BASEPLATE_SHA256, "水施底板与发布版不符")
        sources.update(baseplate=BASEPLATE, style=ASSETS/"pipe-style/水施线形参照.dwg",
                       side=ASSETS/"pipe-style/露台墙侧排口.dwg")
        libraries, equipment = production_libraries()
        for name, (path, sha) in libraries.items():
            require(digest(path) == sha.lower(), "随包原生资产与对象索引不符：" + name)
            sources[name] = path
        spec.setdefault("symbols", {}).update(SIDE_LEFT=dict(source="side", handle="79"),
                                            SIDE_RIGHT=dict(source="side", handle="83"))
        for name, record in equipment.items():
            spec["symbols"][name] = dict(source="pot", handle=record["handle"])
        for item in list(spec["symbols"].values()) + spec["bases"]:
            require(item["source"] in sources, "Unknown DWG source")
        for base in spec["bases"]:
            scale = base.get("scale", 1)
            require(type(scale) in (int,float) and 0 < scale < float("inf"), "底图块等比缩放必须为正有限数")
        frames = spec["frames"]
        require(frames and len({f["name"] for f in frames}) == len(frames), "Unique layouts required")
        check_model_arrangement(frames)
        check_sheet_numbers(spec)
        if not commissioning(spec):
            plan_rain_bowls(spec, equipment["BOWL_PLAN"]["symbol_radius_mm"])
            require("ar" in sources, "逐层立管验收需要建筑原图 ar")
            plan_check = sewage_audit.check(spec, design_sewage_segments(spec["ops"]))
            require(plan_check["passed"], "\n".join(plan_check["errors"]))
            rain = [dict(path=str(i), a=o["a"], b=o["b"]) for i, o in enumerate(spec["ops"])
                    if o["t"] == "p" and o["h"] in ("YPLAN", "YSYS")]
            rain_check = rain_audit.check(spec, rain)
            require(rain_check["passed"], "\n".join(rain_check["errors"]))
        for f in frames:
            x,y,r,t = f["b"]
            require(f["scale"] > 0 and abs(r-x-420*f["scale"]) < .1 and
                    abs(t-y-297*f["scale"]) < .1, "A3 bounds and scale: "+f["name"])
        for op in spec["ops"]:
            require(op["t"] in ("p","s","l","d","n","line","title"), "Unknown operation")
            require(op["h"] in set(PIPES) | {"BOWL"} | spec["symbols"].keys(), "Unknown sample")
            if op["h"] in equipment:
                op.setdefault("layer", equipment[op["h"]]["layer"])
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
    expected = ["architecture.json"] if args.inspect else ["drawing.dwg","aud.json","handles.json","drawing-profile.json","riser-geometry.json"] + [
        f"page{i}.pdf" for i in range(len(spec["frames"]))]
    if not args.inspect:
        shutil.copyfile(HERE/"drawing-profile.json", scripts/"drawing-profile.json")
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
    audit = out/"drawing-profile.json"
    require(audit.is_file(), "缺少成品 DWG 的模型与各布局显示配置回读记录，请用当前 water.py prepare 生成。")
    actual = load(audit)
    require(digest(job/"input/baseplate.dwg") == BASEPLATE_SHA256 and
            actual.get("baseConfig") == "TCH_PSCONFIG", "缺少发布底板或成品天正水施配置")
    expected_views = {"Model", *(frame["name"] for frame in cfg["frames"])}
    require(set(actual["views"]) == expected_views, "显示配置回读未覆盖实际布局")
    profile = load(HERE/"drawing-profile.json")
    for view, values in actual["views"].items():
        require(values == profile, f"{view} 显示配置不符：{values}，应为 {profile}")
    plots = actual.get("plots", {})
    require(set(plots) == expected_views - {"Model"}, "缺少成品布局的打印配置回读")
    for frame in cfg["frames"]:
        name = frame["name"]
        plot = plots[name]
        require(plot["locked"] and abs(plot["scale"] - 1/frame["scale"]) < .000001
                and plot["device"] == "DWG To PDF.pc3"
                and plot["media"] == "ISO_full_bleed_A3_(420.00_x_297.00_MM)"
                and plot["ctb"].lower() == "monochrome.ctb" and plot["plotStyles"],
                f"{name} 的实际视口或 A3 打印配置不符：{plot}")
    require(actual["dwgSha256"] == digest(out/"drawing.dwg"), "成品 DWG 与回读文件不一致")
    for i in range(len(cfg["frames"])):
        require((out/f"page{i}.pdf").read_bytes().startswith(b"%PDF-"), f"Missing PDF {i}")
    handles = load(out/"handles.json")
    rows = {e["h"]: e for e in load(out/"aud.json")}
    if not commissioning(cfg) or (job/"input/ar.dwg").exists():
        evidence = out/"riser-geometry.json"
        try:
            architecture = job/"input/ar.dwg"
            require(architecture.is_file() and
                    digest(architecture) == cfg.get("sources", {}).get("ar", {}).get("sha256", "").lower(),
                    "立管楼层清单对应的建筑原图缺失或已变更")
            require(evidence.is_file(), "缺成品立管及墙柱几何回读，需要用当前技能重开 DWG")
            geometry = load(evidence)
            risers = riser_audit.check(cfg, geometry, actual["dwgSha256"], rows.values())
        except (ValueError, KeyError, TypeError) as exc:
            save(out/"riser-audit.json", dict(dwgSha256=actual["dwgSha256"], passed=False, errors=[str(exc)]))
            raise
        save(out/"riser-audit.json", risers)
        require(risers["passed"], "立管逐层验收失败：\n" + "\n".join(risers["errors"]))
        require("sewage" in geometry and set(geometry.get("sewageLayers", [])) == {"PIPE-污水","S-PIPE-污水"}, "缺少成品平面污水横管回读，请用当前水 SKILL 重新生成")
        sewage = sewage_audit.check(cfg, geometry["sewage"])
        save(out/"sewage-plan-audit.json", dict(dwgSha256=actual["dwgSha256"], **sewage))
        require(sewage["passed"], "\n".join(sewage["errors"]))
        require("rain" in geometry, "缺少成品雨水横管回读，请用当前水 SKILL 重新生成")
        rain = rain_audit.check(cfg, geometry["rain"])
        save(out/"rain-plan-audit.json", dict(dwgSha256=actual["dwgSha256"], **rain))
        require(rain["passed"], "\n".join(rain["errors"]))
    check_model_arrangement(cfg["frames"])
    check_sheet_numbers(cfg)
    for f in cfg["frames"]:
        if "frameBlock" in f:
            boxes = [e["b"] for e in rows.values() if e["t"] == "INSERT" and e["n"] == f["frameBlock"]]
            require(len(boxes) == 1 and boxes[0] and
                    max(abs(x-y) for x,y in zip(boxes[0], f["b"])) <= f["scale"] * .1,
                    "成品模型空间图框与该页窗口不符：" + f["name"])
    require(len(set(handles)) == len(handles) == len(cfg["ops"]), "Incomplete CAD operations")
    style_index = load(ASSETS/"pipe-style/管道线型索引.json")
    require(digest(job/"input/style.dwg") == style_index["sha256"], "管道母版与技能索引不符")
    profiles = style_index["object_profiles"]
    native = {h:p for p in profiles for h in p["handles"]}
    libraries, equipment = production_libraries()
    for name, (_, sha) in libraries.items():
        require(digest(job/("input/"+name+".dwg")) == sha.lower(), "成品任务包母版与索引不符：" + name)
    networks = {}
    for index, (h, op) in enumerate(zip(handles,cfg["ops"])):
        e = rows[h]
        require(e["b"] is not None, f"Missing native extents at operation {index}")
        if e["t"] == "TCH_MULTILEADER":
            require(e.get("leaderArrowStyle") == 0, f"天正引出标注 {h} 的箭头样式应为“无”")
        if op["h"] in equipment:
            expected = equipment[op["h"]]
            require(e["t"] == expected["type"] and e["l"] == op.get("layer",expected["layer"]),
                    "设备原生类型或图层不符：" + h)
        if op["h"] == "BOWL_PLAN":
            x, y, r, t = e["b"]
            cx, cy = op["a"]
            require(point(e["gp"][0]) == point(op["a"]) and r > x and t > y
                    and abs((r-x)/(t-y)-1) < .02 and math.hypot((x+r)/2-cx, (y+t)/2-cy) < .02,
                    "天沟雨水斗平面圆形外轮廓或中心与收水点不符：" + h)
        if op["h"] in ("SIDE_LEFT", "SIDE_RIGHT"):
            require(e["t"] == "TCH_EQUIPMENT" and e["l"] == op.get("layer","EQUIP_雨水")
                    and point(e["gp"][0]) == point(op["a"]), "Side outlet "+h)
        if op["h"] == "WPLAN" and op["t"] == "p" and op["dn"] == 200:
            require(abs(actual["sewageWidths"].get(h, 0) - 60) < .01,
                    "平面 DN200 污水管原生绘制宽度应为 60 模型毫米："+h)
        if op["h"] in PIPES:
            expected = native[PIPES[op["h"]]]
            layer = style_index["layers"][expected["layer"]]
            require(e.get("layerColor") == int(layer["color"]) and
                    e.get("layerType", "").casefold() == layer["linetype"].casefold() and
                    e.get("weight") == "ByLayer", "有效图层或实体线宽不符 "+h)
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
    leader_tips = {point(rows[h]["gp"][2]) for h, op in zip(handles, cfg["ops"])
                   if op["t"] == "l" and op.get("txt", "").strip()}
    used = set()
    for service in cfg.get("services", []):
        for view in ("plan", "system"):
            key = service[view]
            require(key not in used, "Repeated service endpoint "+key)
            used.add(key)
            actual = named[key]
            require(point(service[view+"Point"]) == point(actual["gp"][service.get(view+"Grip",0)]),
                    "Wrong service endpoint "+key)
        anchor = service.get("systemLeaderPoint", service["systemPoint"])
        require(point(anchor) in leader_tips, "房间接口缺少指向实际管端或阀门的天正引注："+service["system"])
    for check in cfg.get("clearances", []):
        x1,y1,x2,y2 = named[check["id"]]["b"]
        margin = check["margin"]
        require(margin >= 0, "Negative clearance")
        for left,bottom,right,top in check["obstacles"]:
            require(x2+margin <= left or x1-margin >= right or y2+margin <= bottom or y1-margin >= top,
                    "Insufficient clearance "+check["id"])
    print(f'{len(cfg["frames"])} layouts, {len(handles)} native operations verified.')


def check_baseline(job):
    """Compare the fixed commissioning sheets using the same renderer for both PDFs."""
    verify(job)
    import pypdfium2 as pdf

    example = load(HERE/"commission.json")
    config = load(job/"scripts/cfg.json")
    require(config["frames"] == example["frames"] and config["ops"] == example["ops"],
            "请使用随库 commission.json 的试图任务")

    # The two commissioning sheets contain one native pipe from each sewage layer.
    handles = load(job/"output/handles.json")
    pipes = load(job/"output/riser-geometry.json")["sewage"]
    for design in design_sewage_segments(config["ops"]):
        handle = handles[int(design["path"])]
        require(any(pipe["path"] == handle and pipe["dn"] == design["dn"] and
                    sewage_audit.close(pipe["a"], design["a"]) and sewage_audit.close(pipe["b"], design["b"])
                    for pipe in pipes), "试图缺少平面或系统污水管的原生回读：" + handle)

    def pixels(path):
        with pdf.PdfDocument(path) as document:
            require(len(document) == 1, f"基准试印应为单页：{path}")
            page = document[0]
            bitmap = page.render(scale=2, grayscale=True)
            try:
                data = bytes(bitmap.buffer)
                row_bytes = bitmap.width * bitmap.n_channels
                visible = b"".join(data[start:start+row_bytes]
                                   for start in range(0, bitmap.height*bitmap.stride, bitmap.stride))
                return page.get_size(), bitmap.width, bitmap.height, visible
            finally:
                bitmap.close()
                page.close()

    # Sample the straight part of the DN200 commissioning pipe, away from its label.
    from statistics import median
    with pdf.PdfDocument(job/"output/page0.pdf") as document:
        page = document[0]
        points_per_mm = 72 / 25.4
        width, height = page.get_size()
        crop = (45 * points_per_mm, 78 * points_per_mm,
                width - 65 * points_per_mm, height - 82 * points_per_mm)
        scale = 12
        bitmap = page.render(scale=scale, crop=crop, grayscale=True)
        try:
            data = bytes(bitmap.buffer)
            middle = bitmap.height // 2
            strokes = []
            for x in range(bitmap.width):
                if data[middle * bitmap.stride + x] >= 128:
                    continue
                top = bottom = middle
                while top > 0 and data[(top - 1) * bitmap.stride + x] < 128:
                    top -= 1
                while bottom + 1 < bitmap.height and data[(bottom + 1) * bitmap.stride + x] < 128:
                    bottom += 1
                strokes.append((bottom - top + 1) / (scale * points_per_mm))
            require(strokes and abs(median(strokes) - 0.60) <= 0.04,
                    "DN200 污水标样的 1:100 纸面宽度与 0.60 mm 基准不符")
        finally:
            bitmap.close()
            page.close()

    for i, frame in enumerate(example["frames"]):
        filename = f"page{i}.pdf"
        require(pixels(job/"output"/filename) == pixels(HERE/"baseline"/filename),
                f'{frame["name"]} 与随库基准纸面或像素有差异，请核对字体、天正及打印配置。')
    print("两张标准试图的纸面尺寸与 144 dpi 灰度渲染均与库内基准一致。")


def review_template(job):
    cfg = load(job/"scripts/cfg.json")
    architecture = job/"input/ar.dwg"
    require(architecture.is_file(), "项目任务包缺少建筑底图 input/ar.dwg")
    pages = {}
    plan_layouts = {plan.get("layout") for plan in cfg.get("riserPlans", [])}
    for i, frame in enumerate(cfg["frames"]):
        name = frame["name"]
        page = {"pdfSha256": digest(job/f"output/page{i}.pdf"), "layoutReview": ""}
        if "平面" in name or name in plan_layouts:
            page.update(baseComparison="", colorAndLineReview="")
            proof = job / "output" / f"model-color-{i}.png"
            page["baseColorProofSha256"] = digest(proof) if proof.is_file() else ""
            page["openingReview"] = {"result": "", "locations": "", "components": ""}
        if "系统" in name:
            page.update(leaderReview="", colorAndLineReview="")
        pages[name] = page
    floors = {floor: "" for floor in cfg["riserStoreys"]}
    return dict(dwgSha256=digest(job/"output/drawing.dwg"),
                architectureSha256=digest(architecture), pages=pages, riserFloorReviews=floors,
                riserScheduleSha256=digest(job/"scripts/cfg.json"),
                riserAuditSha256=digest(job/"output/riser-audit.json"))


def deliver(job, review_path, destination):
    verify(job)
    expected = review_template(job)
    review = load(review_path)
    for field in ("dwgSha256","architectureSha256","riserScheduleSha256","riserAuditSha256"):
        require(review.get(field) == expected[field], "逐页核对记录的文件版本不符："+field)
    floors = review.get("riserFloorReviews", {})
    require(floors.keys() == expected["riserFloorReviews"].keys(), "立管人工回读缺建筑层位")
    for floor, note in floors.items():
        require(isinstance(note, str) and note.strip(), floor + " 缺逐层对照建筑原图及立管清单的核对记录")
    pages = review.get("pages", {})
    require(pages.keys() == expected["pages"].keys(), "逐页核对记录与实际出图清单不符")
    for i, (name, fields) in enumerate(expected["pages"].items()):
        page = pages[name]
        require(page.get("pdfSha256") == fields["pdfSha256"], "需复核本版试印："+name)
        if "openingReview" in fields:
            proof = job / "output" / f"model-color-{i}.png"
            require(fields["baseColorProofSha256"] and
                    page.get("baseColorProofSha256") == fields["baseColorProofSha256"],
                    f"{name} 缺本页彩色模型核对图或文件已变化：{proof.name}")
            from PIL import Image
            with Image.open(proof) as image:
                require(image.format == "PNG" and image.mode in ("RGB", "RGBA", "P"),
                        f"{name} 须提供彩色模型 PNG")
                image.load()
            record = page.get("openingReview")
            require(isinstance(record, dict) and record.get("result") in ("通过", "原图无门窗"),
                    f"{name} 门窗淡显未通过复核")
            for key in ("locations", "components"):
                require(isinstance(record.get(key), str) and record[key].strip(),
                        f"{name} 缺门窗位置、构件或无门窗依据：{key}")
        for field in fields.keys() - {"pdfSha256", "baseColorProofSha256", "openingReview"}:
            require(isinstance(page.get(field), str) and page[field].strip(),
                    f"{name} 缺少 {field} 的实际核对记录")
    require(destination.suffix.lower() == ".dwg", "交付文件应为 DWG")
    drawing = job/"output/drawing.dwg"
    with drawing.open("rb") as src, destination.open("xb") as dst:
        try:
            shutil.copyfileobj(src, dst)
            dst.flush()
            require(digest(destination) == review["dwgSha256"], "交付副本校验失败")
        except BaseException:
            dst.close()
            destination.unlink()
            raise


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
    baseline=modes.add_parser("check-baseline")
    baseline.add_argument("job",type=Path)
    review_cmd=modes.add_parser("review-template")
    review_cmd.add_argument("job",type=Path)
    review_cmd.add_argument("review",type=Path)
    delivery=modes.add_parser("deliver")
    delivery.add_argument("job",type=Path)
    delivery.add_argument("review",type=Path)
    delivery.add_argument("destination",type=Path)
    args=parser.parse_args()
    if args.mode=="prepare":
        prepare(args)
    elif args.mode=="verify":
        verify(args.job)
    elif args.mode=="check-baseline":
        check_baseline(args.job)
    elif args.mode=="review-template":
        template = review_template(args.job)
        with args.review.open("x", encoding="utf-8") as output:
            json.dump(template, output, ensure_ascii=False, indent=2)
    else:
        deliver(args.job, args.review, args.destination)
