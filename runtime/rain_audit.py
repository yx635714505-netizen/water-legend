"""Match rain segments in plan views to located ground-level ditch outlets."""
import re

from riser_audit import inside, numbers, plan_windows
from sewage_audit import close, intersects, outside_plan_windows


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
    errors.extend(outside_plan_windows(cfg, windows, segments, "雨水"))
    return dict(passed=not errors, floors=floors, errors=errors)
