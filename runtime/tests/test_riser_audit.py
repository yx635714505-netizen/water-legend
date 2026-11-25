import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import riser_audit as audit


class RiserAuditTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(frames=[], riserStoreys=["首层", "二层"], riserPlans=[])
        self.geometry = dict(version=1, dwgSha256="test", objects=[])
        for i, floor in enumerate(self.cfg["riserStoreys"]):
            x = i * 2000
            name = floor + "平面图"
            at = [x+200, 150]
            self.cfg["frames"].append(dict(name=name, b=[x, 0, x+1000, 1000]))
            item = dict(number="JG-1", layer="VPIPE-给水", at=at[:], outerDiameter=50, clearance=15)
            self.cfg["riserPlans"].append(dict(layout=name, floor=floor, sourceRef=floor, risers=[item]))
            self.geometry["objects"].extend([
                dict(kind="riser", path=f"{i}/AB", at=at, layer=item["layer"], dn=40),
                dict(kind="barrier", path=f"{i}/CD", exact=True,
                     polygon=[[x,100],[x+100,100],[x+100,200],[x,200]])])

    def result(self):
        return audit.check(self.cfg, self.geometry, "test", [])

    def test_clear_two_storeys_and_reused_block(self):
        result = self.result()
        self.assertTrue(result["passed"])
        self.assertEqual([p["checks"][0]["netClearance"] for p in result["floors"]], [75,75])

    def test_missing_floor(self):
        self.cfg["riserPlans"].pop()
        with self.assertRaisesRegex(ValueError, "楼层"):
            self.result()

    def test_absent_layout_even_if_schedule_also_omitted(self):
        self.cfg["riserPlans"].pop()
        self.cfg["riserStoreys"].pop()
        with self.assertRaisesRegex(ValueError, "遗漏平面"):
            self.result()

    def test_missing_actual_riser(self):
        self.geometry["objects"].pop(2)
        self.assertIn("二层 JG-1", self.result()["errors"][0])

    def test_unlisted_actual_riser(self):
        plan = self.cfg["riserPlans"][1]
        plan.update(risers=[], emptyReason="申报为零根")
        self.assertIn("漏查", self.result()["errors"][0])

    def test_pipe_edge_and_installation_clearance(self):
        for x in [80, 120, 125, 135]:
            self.cfg["riserPlans"][0]["risers"][0]["at"][0] = x
            self.geometry["objects"][0]["at"][0] = x
            self.assertFalse(self.result()["passed"])

    def test_rain_embed_requires_exact_named_host(self):
        item = self.cfg["riserPlans"][0]["risers"][0]
        actual, wall = self.geometry["objects"][:2]
        item.update(at=[50,150], embeddedHost=wall["path"])
        actual["at"] = item["at"][:]
        self.assertFalse(self.result()["passed"])
        item["layer"] = actual["layer"] = "VPIPE-雨水"
        self.assertTrue(self.result()["passed"])
        wall["exact"] = False
        self.assertFalse(self.result()["passed"])

    def test_hash_and_unresolved_outline(self):
        self.geometry["objects"][1]["kind"] = "unknown"
        self.assertFalse(self.result()["passed"])
        self.geometry["dwgSha256"] = "older"
        with self.assertRaisesRegex(ValueError, "DWG"):
            self.result()
