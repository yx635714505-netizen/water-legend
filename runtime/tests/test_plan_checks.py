import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sewage_audit
import water


class PlanChecks(unittest.TestCase):
    def test_sheet_order(self):
        def check(titles):
            frames = [dict(name="水施-A00 目录")] + [
                dict(name=f"水施-B{i:02d} {title}") for i, title in enumerate(titles, 1)]
            water.check_sheet_numbers(dict(frames=frames))
        check(["首层平面图", "屋顶平面图", "给水系统图", "排水系统图"])
        for titles in (["系统图", "首层平面图"], ["首层平面图", "系统图", "屋顶平面图"]):
            with self.subTest(titles=titles), self.assertRaises(ValueError):
                check(titles)

    def test_sewage_on_shared_sheet(self):
        layout = "合页平面图"
        names = ["首层", "二层"]
        plans = [dict(floor=name, sourceRef=name, layout=layout, window=[x,0,x+90,100],
                      risers=[], emptyReason="只检查横管") for name, x in zip(names,[0,110])]
        cfg = dict(frames=[dict(name=layout,b=[0,0,200,100]),dict(name="系统图",b=[300,0,400,100])],
                   riserStoreys=names, riserPlans=plans)
        for a,b,ok in [(95,105,False),(75,125,False),(-20,220,False),(310,390,True)]:
            with self.subTest(a=a,b=b):
                pipe = dict(path="F",dn=100,a=[a,50],b=[b,50])
                self.assertEqual(sewage_audit.check(cfg,[pipe])["passed"],ok)

    def test_prepare_collects_both_sewage_samples(self):
        ops = [dict(t="p",h=h,a=[0,0],b=[5,0],dn=100) for h in ("WPLAN","WSYS","JSYS")]
        self.assertEqual([p["path"] for p in water.design_sewage_segments(ops)], ["0","1"])
