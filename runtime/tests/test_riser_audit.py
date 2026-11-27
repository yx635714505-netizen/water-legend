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
                dict(kind="barrier", path=f"{i}/CA/CD", exact=True,
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

    def make_joint(self):
        item = self.cfg["riserPlans"][0]["risers"][0]
        pipe, host = self.geometry["objects"][:2]
        item.update(at=[50,150], layer="VPIPE-雨水", embeddedHost=host["path"])
        pipe.update(at=item["at"][:], layer=item["layer"])
        host.update(type="LWPOLYLINE", layer="建-柱-砼")
        wall = dict(kind="barrier", type="TCH_WALL", layer="WALL", path="0/EE",
                    exact=False, polygon=[[0,120],[160,120],[160,180],[0,180]])
        self.geometry["objects"].append(wall)
        self.cfg.update(sources={"ar":{"sha256":"a"*64}},bases=[
            dict(name="fixture",source="ar",ids=["6A","6B"])])
        item["embeddedWallEvidence"] = dict(source="ar", sha256="a"*64, base="fixture",
            columnBlock="6A", hatch="BE", outline=[p[:] for p in host["polygon"]],
            walls=[dict(path=wall["path"], sourceWall="6B",
                        axis=[[0,150],[160,150]], bounds=[0,120,160,180])])
        self.geometry["jointProofs"] = [dict(base="fixture", source="ar", sourceSha256="a"*64,
            importedSource="ar", importedSha256="a"*64, columnBlock="6A", hatch="BE",
            columnPath="0/CA", outline=host["polygon"], importedOutline=host["polygon"], wallPaths={"6B":wall["path"]})]
        return item, wall

    def test_named_native_wall_concrete_joint(self):
        item, wall = self.make_joint()
        result = self.result()
        self.assertTrue(result["passed"], result["errors"])
        check = result["floors"][0]["checks"][0]
        self.assertEqual(check["wallColumnJoints"][0]["path"], wall["path"])
        self.assertEqual(check["wallColumnJoints"][0]["remainingWallGapLowerBound"],25)
        del item["embeddedWallEvidence"]
        self.assertFalse(self.result()["passed"])

    def test_joint_never_ignores_other_wall_or_pipe_edge(self):
        item, wall = self.make_joint()
        self.geometry["objects"].append(dict(wall,path="0/FF",polygon=[[1,120],[160,120],[160,180],[1,180]]))
        self.assertFalse(self.result()["passed"])
        self.geometry["objects"].pop()
        item["clearance"] = 26
        self.assertFalse(self.result()["passed"])

    def test_joint_uses_new_clone_paths_and_rejects_duplicate_geometry(self):
        item, wall = self.make_joint()
        host = self.geometry["objects"][1]
        host["path"], wall["path"] = "8/44/77", "8/99"
        self.geometry["jointProofs"][0].update(columnPath="8/44", wallPaths={"6B":"8/99"})
        check = self.result()["floors"][0]["checks"][0]
        self.assertEqual(check["embeddedHost"], "8/44/77")
        self.assertEqual(check["wallColumnJoints"][0]["path"], "8/99")
        self.geometry["objects"].append(dict(host, path="8/44/CC"))
        with self.assertRaises(ValueError):
            self.result()
        self.geometry["objects"].pop()
        self.geometry["objects"].append(dict(wall, path="8/BB"))
        self.assertFalse(self.result()["passed"])

    def test_classified_copy_must_match_both_source_outlines(self):
        self.make_joint()
        self.cfg["bases"][0]["source"] = "clean"
        self.cfg["sources"]["clean"] = {"sha256":"b"*64}
        proof = self.geometry["jointProofs"][0]
        proof.update(importedSource="clean", importedSha256="b"*64)
        self.assertTrue(self.result()["passed"])
        proof["importedOutline"] = [[0,0],[1,0],[0,1]]
        with self.assertRaises(ValueError):
            self.result()

    def test_joint_rejects_unbound_geometry(self):
        for change in ("checksum","sourceWall","wallType","hostType","axis","outline","duplicate"):
            with self.subTest(change=change):
                self.setUp()
                item, wall = self.make_joint()
                ev = item["embeddedWallEvidence"]
                if change == "checksum": ev["sha256"]="x"*64
                if change == "sourceWall": ev["walls"][0]["sourceWall"]="ABCD"
                if change == "wallType": wall["type"]="LINE"
                if change == "hostType": self.geometry["objects"][1]["layer"]="屋面线"
                if change == "axis": ev["walls"][0]["axis"][0][0]+=10
                if change == "outline": ev["outline"][0][0]+=1
                if change == "duplicate": ev["walls"].append(ev["walls"][0])
                with self.assertRaises(ValueError):
                    self.result()

    def test_joint_requires_proof_from_actual_import(self):
        for change in ("source", "hatch", "missing", "otherColumn", "otherWall", "otherOutline"):
            with self.subTest(change=change):
                self.setUp()
                item, wall = self.make_joint()
                proof = self.geometry["jointProofs"][0]
                if change == "source":
                    self.cfg["sources"]["other"] = {"sha256":"b"*64}
                    self.cfg["bases"][0]["source"] = "other"
                if change == "hatch": item["embeddedWallEvidence"]["hatch"] = "DEADBEEF"
                if change == "missing": del self.geometry["jointProofs"]
                if change == "otherColumn": proof["columnPath"] = "0/FF"
                if change == "otherWall": proof["wallPaths"]["6B"] = "0/FF"
                if change == "otherOutline": proof["outline"] = [[0,0],[1,0],[0,1]]
                with self.assertRaises(ValueError):
                    self.result()

    def test_hash_and_unresolved_outline(self):
        self.geometry["objects"][1]["kind"] = "unknown"
        self.assertFalse(self.result()["passed"])
        self.geometry["dwgSha256"] = "older"
        with self.assertRaisesRegex(ValueError, "DWG"):
            self.result()
