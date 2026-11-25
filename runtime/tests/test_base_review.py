import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import water


class BaseReviewTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.job = Path(temp.name)
        for dirname in ("scripts", "input", "output"):
            (self.job / dirname).mkdir()
        water.save(self.job / "scripts/cfg.json", {
            "frames": [{"name": "目录"}, {"name": "首层布置"}],
            "riserPlans": [{"floor": "首层", "layout": "首层布置"}],
            "riserStoreys": ["首层"],
        })
        for name in ("input/ar.dwg", "output/drawing.dwg", "output/riser-audit.json",
                     "output/page0.pdf", "output/page1.pdf"):
            (self.job / name).write_bytes(b"fixture")
        self.image = self.job / "output/model-color-1.png"
        Image.new("RGB", (8, 8), "gray").save(self.image)
        self.review = water.review_template(self.job)
        self.review["riserFloorReviews"]["首层"] = "已核对首层"
        self.review["pages"]["目录"]["layoutReview"] = "目录已核对"
        self.page = self.review["pages"]["首层布置"]
        self.page.update(layoutReview="首层", baseComparison="外围尺寸齐全",
                         colorAndLineReview="阀门与建筑可区分",
                         openingReview=dict(result="通过", locations="首层 A–D 轴",
                                            components="窗框、玻璃和门扇开启弧均为灰色"))

    def deliver(self):
        review = self.job / "review.json"
        water.save(review, self.review)
        with patch.object(water, "verify"):
            water.deliver(self.job, review, self.job / "delivery.dwg")

    def test_complete_plan_review(self):
        self.deliver()

    def test_old_or_failed_review_is_rejected(self):
        self.page["openingReview"]["result"] = "北侧窗框黄色"
        with self.assertRaisesRegex(ValueError, "淡显未通过"):
            self.deliver()
        del self.page["openingReview"]
        with self.assertRaisesRegex(ValueError, "淡显未通过"):
            self.deliver()

    def test_missing_or_replaced_proof_is_rejected(self):
        self.image.unlink()
        with self.assertRaisesRegex(ValueError, "彩色模型核对图"):
            self.deliver()
        Image.new("RGB", (8, 8), "yellow").save(self.image)
        with self.assertRaisesRegex(ValueError, "彩色模型核对图"):
            self.deliver()

    def test_no_openings_requires_source_basis(self):
        self.page["openingReview"].update(result="原图无门窗", locations="屋顶", components="")
        with self.assertRaisesRegex(ValueError, "无门窗依据"):
            self.deliver()
