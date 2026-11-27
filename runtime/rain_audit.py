"""Match rain segments in plan views to located ground-level ditch outlets."""
import re

from riser_audit import inside, numbers, plan_windows
from sewage_audit import close, intersects


def check(cfg, segments):
    errors, floors = [], []
    windows = plan_windows(cfg)
    for plan, box in windows:
        floor = plan["floor"]
        routes = plan.get("rainDitchRoutes", [])
        expected = {}
        for route in routes:
            number = route["riser"]
            ground = floor == cfg.get("groundStorey") or re.fullmatch(
                r"(首层|底层|地面层|一层|第一层|1层|1F|F1|室外)(平面(图)?)?", floor.strip(), re.I)
            if not plan.get("layout") or not ground:
                raise ValueError(f"{floor} 仅首层及对应室外平面允许接沟")
            item = next((r for r in plan["risers"] if r["number"] == number and "雨水" in r["layer"]), None)
            inlet = route["ditchPoint"]
            if (not item or number in expected or not route.get("sourceRef", "").strip()
                    or not numbers(inlet, 2) or not inside(box, inlet) or close(item["at"], inlet)):
                raise ValueError(f"{floor} {number} 缺少唯一的落地雨水立管、原图沟口坐标或依据")
            expected[number] = (item["at"], inlet)
        paths = []
        for pipe in segments:
            a, b = pipe["a"], pipe["b"]
            if not intersects(box, a, b):
                continue
            paths.append(pipe["path"])
            match = next((n for n, (p, q) in expected.items() if
                          (close(a, p) and close(b, q)) or (close(a, q) and close(b, p))), None)
            if match is None:
                errors.append(f"{floor} 多余或接沟端点不符的雨水平面横管 {pipe['path']}")
            else:
                del expected[match]
        errors.extend(f"{floor} {number} 缺少接沟管" for number in expected)
        floors.append(dict(floor=floor, paths=paths))
    # On a shared sheet also inspect strips of paper outside all floor windows.
    layouts = {p.get("layout") for p, _ in windows}
    for frame in cfg["frames"]:
        if frame["name"] not in layouts:
            continue
        for pipe in segments:
            a, b = pipe["a"], pipe["b"]
            if intersects(frame["b"], a, b) and not any(
                    p.get("layout") == frame["name"] and inside(box, a) and inside(box, b)
                    for p, box in windows):
                errors.append(f"{frame['name']} 雨水横管越出本层核对窗口 {pipe['path']}")
    return dict(passed=not errors, floors=floors, errors=errors)
