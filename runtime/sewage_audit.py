"""Match native plan sewage segments against the approved outlet routes in model mm."""
from math import hypot

from riser_audit import inside, numbers, plan_windows


def intersects(box, a, b):
    low, high = 0.0, 1.0
    for axis in (0, 1):
        delta = b[axis] - a[axis]
        if not delta:
            if not box[axis] <= a[axis] <= box[axis + 2]:
                return False
            continue
        near, far = sorted((bound - a[axis]) / delta for bound in (box[axis], box[axis + 2]))
        low, high = max(low, near), min(high, far)
    return low <= high


def close(a, b):
    return hypot(a[0] - b[0], a[1] - b[1]) <= 0.02


def check(cfg, segments):
    results, errors = [], []
    for floor, box in plan_windows(cfg):
        remaining = []
        for route in floor.get("sewageRoutes", []):
            use, pts = route["use"], route["points"]
            if use not in ("出户及室外", "项目明确器具详接") or (
                    use == "项目明确器具详接" and not route.get("sourceRef", "").strip()):
                raise ValueError(f"{floor['floor']} 污水横管用途或器具详接依据缺失")
            if len(pts) < 2 or not all(numbers(p, 2) and inside(box, p) for p in pts):
                raise ValueError(f"{floor['floor']} 污水横管清单坐标无效")
            remaining.extend((a, b, route["dn"]) for a, b in zip(pts, pts[1:]))
        paths = []
        for pipe in segments:
            a, b = pipe["a"], pipe["b"]
            if not intersects(box, a, b):
                continue
            paths.append(pipe["path"])
            for index, (p, q, dn) in enumerate(remaining):
                if dn == pipe["dn"] and ((close(a, p) and close(b, q)) or
                                         (close(a, q) and close(b, p))):
                    remaining.pop(index)
                    break
            else:
                errors.append(f"{floor['floor']} 多余或位置、管径不符的平面污水横管 {pipe['path']}")
        for a, b, dn in remaining:
            errors.append(f"{floor['floor']} 缺少已核定平面污水横管 DN{dn} {a} 至 {b}")
        results.append(dict(floor=floor["floor"], paths=paths))
    return dict(passed=not errors, floors=results, errors=errors)
