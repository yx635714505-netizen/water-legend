"""Compare the architectural floor/riser schedule with reopened model-space geometry (mm)."""
from math import hypot, isfinite


def require(ok, message):
    if not ok:
        raise ValueError(message)


def numbers(value, count):
    return (isinstance(value, list) and len(value) == count
            and all(type(x) in (int, float) and isfinite(x) for x in value))


def inside(box, point):
    x, y = point
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def overlaps(a, b):
    return a[0] <= b[2] and a[1] <= b[3] and b[0] <= a[2] and b[1] <= a[3]


def plan_windows(cfg):
    frames = {f["name"]: f["b"] for f in cfg["frames"]}
    needed = {name for name in frames if "平面" in name or not any(
        word in name for word in ("目录", "说明", "图例", "系统", "详图"))}
    floors = cfg.get("riserStoreys")
    require(isinstance(floors, list) and floors and all(isinstance(f, str) and f.strip() for f in floors)
            and len(floors) == len(set(floors)), "缺少建筑原图的完整、唯一楼层清单 riserStoreys")
    plans = cfg.get("riserPlans")
    require(isinstance(plans, list) and plans, "缺少逐层立管清单 riserPlans")
    windows = []
    for p in plans:
        layout, floor = p.get("layout"), p["floor"]
        require(floor in floors and p.get("sourceRef", "").strip(), f"{floor} 缺建筑图号、层位依据")
        require(layout in frames or (layout is None and p.get("omissionReason", "").strip()),
                f"{floor} 缺实际布局或免出平面依据")
        box = p.get("window", frames.get(layout))
        require(numbers(box, 4) and box[0] < box[2] and box[1] < box[3], f"{floor} 验收窗口无效")
        if layout:
            require(inside(frames[layout], box[:2]) and inside(frames[layout], box[2:]), f"{floor} 窗口越出图框")
        else:
            require(not any(overlaps(box, frame) for frame in frames.values()), f"{floor} 隐藏核对区与出图窗口重叠")
        require(not any(overlaps(box, prev) for _, prev in windows), f"{floor} 核对区重复或相交")
        windows.append((p, box))
        items = p.get("risers")
        require(isinstance(items, list) and (items or p.get("emptyReason", "").strip()), f"{floor} 缺立管或零根依据")
        ids = set()
        for item in items:
            name = item["number"]
            require(isinstance(name, str) and name.strip() and name not in ids, f"{floor} 立管编号重复或为空")
            ids.add(name)
            require(numbers(item["at"], 2) and inside(box, item["at"]) and item["layer"].strip(),
                    f"{floor} {name} 缺有效轴位或图层")
            size = [item.get("outerDiameter"), item.get("clearance")]
            require(numbers(size, 2) and size[0] > 0 and size[1] >= 0, f"{floor} {name} 缺管外径或安装净距")
    require({p["floor"] for p, _ in windows} == set(floors), "逐根核对未覆盖建筑原图全部楼层")
    missing = needed - {p.get("layout") for p, _ in windows}
    require(not missing, "遗漏平面布局：" + "、".join(sorted(missing)))
    return windows


def signed_distance(point, polygon):
    """Positive outside, negative inside; tolerant of repeated vertices."""
    x, y = point
    best, interior = float("inf"), False
    for i, (ax, ay) in enumerate(polygon):
        bx, by = polygon[i-1]
        dx, dy = bx-ax, by-ay
        length2 = dx*dx + dy*dy
        t = max(0, min(1, ((x-ax)*dx + (y-ay)*dy)/length2)) if length2 else 0
        best = min(best, hypot(x-ax-t*dx, y-ay-t*dy))
        if (ay > y) != (by > y) and x < ax + (y-ay)*dx/dy:
            interior = not interior
    return -best if interior else best


def same_outline(a, b):
    if len(a) != len(b) or not a:
        return False
    for i, point in enumerate(b):
        if hypot(a[0][0]-point[0], a[0][1]-point[1]) > .02:
            continue
        for step in (1, -1):
            if all(hypot(x-b[(i+step*j) % len(b)][0], y-b[(i+step*j) % len(b)][1]) <= .02
                   for j, (x, y) in enumerate(a)):
                return True
    return False


def wall_column_joints(cfg, item, pipe, nearby, proofs):
    """Validate a source-traced native wall meeting the same physical concrete column."""
    if "embeddedWallEvidence" not in item:
        return item.get("embeddedHost"), {}
    ev = item["embeddedWallEvidence"]
    require(isinstance(ev, dict) and isinstance(item.get("embeddedHost"), str)
            and item["embeddedHost"] and "雨水" in pipe["layer"], "墙柱交接原图证据或预埋管类无效")
    require(ev.get("source") == "ar", "墙柱交接证据须追溯至建筑原图 ar")
    original = cfg.get("sources", {}).get("ar", {})
    checksum = ev.get("sha256")
    require(isinstance(checksum, str) and len(checksum) == 64
            and all(c in "0123456789abcdef" for c in checksum.lower())
            and original.get("sha256", "").lower() == checksum.lower(), "墙柱交接原图散列不符")
    bases = [b for b in cfg.get("bases", []) if b["name"] == ev.get("base")]
    require(len(bases) == 1 and ev.get("columnBlock") in bases[0]["ids"]
            and isinstance(ev.get("hatch"), str) and ev["hatch"]
            and all(c in "0123456789ABCDEF" for c in ev["hatch"].upper()),
            "墙柱交接缺原图柱实例或填充句柄")
    expected = ev.get("outline")
    require(isinstance(expected, list) and len(expected) >= 3 and
            all(numbers(p, 2) for p in expected), "缺少原图柱面顶点")
    imported = bases[0].get("source")
    records = [p for p in proofs if p["base"] == ev["base"] and p["source"] == ev["source"]
               and p["sourceSha256"] == checksum.lower() and p["importedSource"] == imported
               and p["importedSha256"] == cfg["sources"].get(imported, {}).get("sha256", "").lower()
               and p["columnBlock"] == ev["columnBlock"] and p["hatch"] == ev["hatch"]]
    require(len(records) == 1 and same_outline(expected, records[0]["outline"])
            and same_outline(expected, records[0]["importedOutline"]),
            "原图柱填充与实际导入底图的回读证据不符，请重新出图")
    proof = records[0]
    hosts = [o for o in nearby if o["kind"] == "barrier" and o["exact"] and
             (o.get("type") == "TCH_COLUMN" or
              (o.get("type") == "LWPOLYLINE" and
               o.get("layer", "").split("$")[-1] in {"建-柱-砼", "建-柱-验算"}))
             and o["path"].startswith(proof["columnPath"] + "/") and same_outline(expected, o["polygon"])]
    require(len(hosts) == 1, "成品未唯一对应原图混凝土柱轮廓")
    host = hosts[0]
    polygon = host["polygon"]
    walls = ev.get("walls")
    require(isinstance(walls, list) and walls, "未列明具体墙柱交接")
    records = {}
    for row in walls:
        require(isinstance(row, dict) and row.get("sourceWall") in bases[0]["ids"],
                "墙柱交接未对应原图墙句柄")
        bounds, axis = row.get("bounds"), row.get("axis")
        require(numbers(bounds, 4) and isinstance(axis, list) and len(axis) == 2
                and all(numbers(p, 2) for p in axis), "缺少原墙轴端与边界")
        left, bottom, right, top = bounds
        corners = [[left,bottom],[right,bottom],[right,top],[left,top]]
        require(right > left and top > bottom, "原墙边界为空")
        matches = [o for o in nearby if o["kind"] == "barrier" and o.get("type") == "TCH_WALL"
                   and o["path"] == proof["wallPaths"].get(row["sourceWall"]) and len(o["polygon"]) == 4
                   and all(any(hypot(x-u,y-v) <= .02 for u,v in o["polygon"]) for x,y in corners)]
        require(len(matches) == 1 and matches[0]["path"] not in records,
                "同一底图的成品原生墙不能按原图边界唯一对应")
        wall = matches[0]
        (x1,y1),(x2,y2) = sorted(axis)
        horizontal = max(abs(x1-left), abs(x2-right),
                         abs(y1-(bottom+top)/2), abs(y2-(bottom+top)/2)) <= .02
        (x1,y1),(x2,y2) = sorted(axis,key=lambda p:p[1])
        vertical = max(abs(y1-bottom), abs(y2-top),
                       abs(x1-(left+right)/2), abs(x2-(left+right)/2)) <= .02
        require(horizontal or vertical, "原生墙轴端未对应墙体实际跨度")
        require(signed_distance(pipe["at"], wall["polygon"]) <= .02, "管位不在原墙与柱的交接投影内")
        # Real masonry outside this column is a subset of the column exterior.
        # The exact host inset is therefore a conservative LOWER bound to W minus C.
        gap = -signed_distance(pipe["at"], polygon) - item["outerDiameter"]/2
        records[wall["path"]] = dict(path=wall["path"], sourceWall=row["sourceWall"],
            sourceConcreteHatch=ev["hatch"], host=host["path"], remainingWallGapLowerBound=gap)
    return host["path"], records


def check(cfg, geometry, sha, audit_rows):
    windows = plan_windows(cfg)
    require(geometry.get("version") == 1 and geometry.get("dwgSha256") == sha,
            "立管和墙柱回读与成品 DWG 不一致")
    require(set(geometry.get("barrierLayers", [])) == set(cfg.get("barrierLayers", [])),
            "墙柱补充图层已改变，需要重新回读 DWG")
    objects = geometry["objects"]
    require(len({o["path"] for o in objects}) == len(objects), "回读对象实例路径重复")
    pipes, obstacles = [], []
    for o in objects:
        if o["kind"] == "riser":
            require(numbers(o["at"], 2) and o["dn"] > 0, "原生立管夹点或管径无效 " + o["path"])
            pipes.append(o)
        else:
            poly = o["polygon"]
            require(o["kind"] in ("barrier", "unknown") and len(poly) >= 3
                    and all(numbers(p, 2) for p in poly), "墙柱轮廓回读无效 " + o["path"])
            xs, ys = zip(*poly)
            obstacles.append((o, [min(xs), min(ys), max(xs), max(ys)]))
    top = {p["path"] for p in pipes if "/" not in p["path"]}
    require(top == {e["h"] for e in audit_rows if e["t"] == "TCH_PIPE" and
                    (e["l"].upper().startswith("VPIPE") or len(e["gp"]) == 1)}, "两次成品对象枚举的立管不一致")
    results, errors, claimed = [], [], set()
    for p, box in windows:
        floor = p["floor"]
        found = [o for o in pipes if inside(box, o["at"])]
        margin = max((item["outerDiameter"]/2 + item["clearance"] for item in p["risers"]), default=0)
        envelope = [box[0]-margin, box[1]-margin, box[2]+margin, box[3]+margin]
        nearby = [o for o, bounds in obstacles if overlaps(envelope, bounds)]
        if not nearby and not p.get("noBarrierSource", "").strip():
            errors.append(f"{floor} 未读到墙柱，缺少原图中本层无墙柱的依据")
        for barrier in nearby:
            if barrier["kind"] == "unknown":
                errors.append(f"{floor} 建筑对象无法确认为墙柱实体 {barrier['path']}")
        rows = []
        for item in p["risers"]:
            label = floor + " " + item["number"]
            matches = [o for o in found if o["layer"] == item["layer"] and
                       hypot(o["at"][0]-item["at"][0], o["at"][1]-item["at"][1]) <= 0.02]
            if len(matches) != 1 or matches[0]["path"] in claimed:
                errors.append(label + " 未能唯一匹配成品立管")
                continue
            pipe = matches[0]
            claimed.add(pipe["path"])
            radius = item["outerDiameter"]/2
            host, joints = wall_column_joints(cfg, item, pipe, nearby, geometry.get("jointProofs", []))
            failures = []
            distances = []
            if host and ("雨水" not in pipe["layer"] or host not in {o["path"] for o in nearby}):
                failures.append("预埋宿主或管类不符")
            for o in nearby:
                d = signed_distance(pipe["at"], o["polygon"])
                if o["path"] == host:
                    if o["kind"] != "barrier" or not o["exact"]:
                        failures.append("预埋宿主缺精确轮廓 " + host)
                    d = -d
                gap = d - radius
                if o["path"] in joints:
                    gap = joints[o["path"]]["remainingWallGapLowerBound"]
                distances.append((gap, o["path"]))
                if gap <= 0 or gap + 1e-6 < item["clearance"]:
                    failures.append(f"墙柱 {o['path']} 管外缘净距 {gap:.2f} mm")
            errors.extend(label + " " + error for error in failures)
            nearest = min(distances) if distances else (None, None)
            rows.append(dict(number=item["number"], handle=pipe["path"], at=pipe["at"],
                             outerDiameter=item["outerDiameter"], requiredClearance=item["clearance"],
                             embeddedHost=host, wallColumnJoints=list(joints.values()), nearestBarrier=nearest[1], netClearance=nearest[0], errors=failures))
        results.append(dict(floor=floor, layout=p.get("layout"), expected=len(p["risers"]),
                            detected=len(found), barriers=len(nearby), checks=rows))
    # Include the whole paper window, including gaps between multi-floor subwindows.
    excluded = [f["b"] for f in cfg["frames"] if f["name"] not in {p.get("layout") for p,_ in windows}
                and any(w in f["name"] for w in ("目录","图例","说明","系统","详图"))]
    for pipe in pipes:
        if pipe["path"] not in claimed and not any(inside(box, pipe["at"]) for box in excluded):
            errors.append(f"成品立管漏查 {pipe['layer']} {pipe['path']} {pipe['at']}")
    return dict(dwgSha256=sha, passed=not errors, floors=results, errors=errors)
