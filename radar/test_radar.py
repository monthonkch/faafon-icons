"""ทดสอบส่วนคำนวณของเรดาร์ (ไม่ต่อเน็ต): python -m unittest discover -s radar -p 'test_*.py'"""
import os, sys, unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radar, clip  # noqa: E402

ICT = timezone(timedelta(hours=7))


def grid(cells):
    return {"cells": "".join(f"{r:03d}{c:03d}{lv}" for (r, c), lv in cells.items())}


class Motion(unittest.TestCase):
    def blob(self, r0, c0):
        return {(r0 + i, c0 + j): 2 for i in range(8) for j in range(8)}

    def test_cells_roundtrip(self):
        g = grid({(1, 2): 3, (370, 260): 1})
        self.assertEqual(radar.cells_of(g), {(1, 2): 3, (370, 260): 1})

    def test_motion_finds_shift(self):
        m = radar.motion(grid(self.blob(100, 100)), grid(self.blob(103, 98)), 30)
        self.assertEqual(m["g"][:2], [3, -2])
        self.assertEqual(m["dt"], 30)

    def test_too_little_rain(self):
        self.assertIsNone(radar.motion(grid({(1, 1): 1}), grid({(1, 2): 1}), 15)["g"])


class Clip(unittest.TestCase):
    def ref(self, t, n):
        ts = lambda i: int((t - timedelta(hours=1) + timedelta(minutes=15 * i)).timestamp())
        png = [{"name": f"radar_ts{ts(i)}_z7.png", "url": f"https://wxmap.tmd.go.th/r/{i}.png"} for i in range(n)]
        return {"ref_time": t.strftime("%Y%m%d%H%M%S"), "profiles": {"thailand": {"png": png}, "bangkok": {"png": png}}}

    def test_pick_full_run(self):
        t = datetime(2026, 10, 22, 12, 0, tzinfo=ICT)
        r = clip.pick_ref({"ref_times": [self.ref(t + timedelta(minutes=15), 4), self.ref(t, 17)]})
        self.assertEqual(r["ref_time"], "20261022120000")

    def test_full_run_too_old(self):
        t = datetime(2026, 10, 22, 12, 0, tzinfo=ICT)
        self.assertIsNone(clip.pick_ref({"ref_times": [self.ref(t + timedelta(minutes=45), 4), self.ref(t, 17)]}))

    def test_frames_sorted_and_host_checked(self):
        t = datetime(2026, 10, 22, 12, 0, tzinfo=ICT)
        r = self.ref(t, 17)
        r["profiles"]["thailand"]["png"].append({"name": "radar_ts1_z.png", "url": "https://evil.example/x.png"})
        fr = clip.frames_of(r, "thailand")
        self.assertEqual(len(fr), 17)
        self.assertEqual(fr[0][0], t - timedelta(hours=1))
        self.assertTrue(all(u.startswith("https://wxmap.tmd.go.th/") for _, u in fr))


if __name__ == "__main__":
    unittest.main()
