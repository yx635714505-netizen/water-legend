import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rain_audit


class RainAuditTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(frames=[], riserStoreys=["首层", "露台层"], riserPlans=[])
        for index, floor in enumerate(self.cfg["riserStoreys"]):
            x = 2000 * index
            name = floor + "平面图"
            self.cfg["frames"].append(dict(name=name, b=[x, 0, x+1000, 1000]))
            riser = dict(number="YL-1", layer="VPIPE-雨水", at=[x+100, 100],
                         outerDiameter=110, clearance=15)
            self.cfg["riserPlans"].append(dict(floor=floor, layout=name, sourceRef=floor, risers=[riser]))
        self.cfg["frames"].append(dict(name="雨水系统图", b=[4000, 0, 5000, 1000]))
        self.ground = dict(path="A", a=[100, 100], b=[800, 300])
        self.terrace = dict(path="B", a=[2100, 100], b=[2800, 300])
        self.system = dict(path="C", a=[4100, 100], b=[4800, 300])
        self.ditch = dict(riser="YL-1", ditchPoint=[800, 300], sourceRef="建施总平面 4/A")

    def test_default_plan_windows_and_system(self):
        self.assertTrue(rain_audit.check(self.cfg, [self.system])["passed"])
        result = rain_audit.check(self.cfg, [self.ground, self.terrace, self.system])
        self.assertEqual(len(result["errors"]), 2)

    def test_located_ditch_is_required_once(self):
        self.cfg["riserPlans"][0]["rainDitchRoutes"] = [self.ditch]
        self.assertTrue(rain_audit.check(self.cfg, [self.ground, self.system])["passed"])
        self.assertFalse(rain_audit.check(self.cfg, [])["passed"])
        self.assertFalse(rain_audit.check(self.cfg, [self.ground, self.ground])["passed"])
        self.assertFalse(rain_audit.check(self.cfg, [dict(self.ground, b=[801, 300])])["passed"])

    def test_upper_floor_cannot_declare_ditch(self):
        self.cfg["riserPlans"][1]["rainDitchRoutes"] = [dict(self.ditch, ditchPoint=[2800, 300])]
        with self.assertRaisesRegex(ValueError, "仅首层"):
            rain_audit.check(self.cfg, [self.terrace])
