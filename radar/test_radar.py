"""ทดสอบส่วนคำนวณของเรดาร์ (ไม่ต่อเน็ต): python -m unittest discover -s radar -p 'test_*.py'"""
import os, sys, unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radar, clip, stations  # noqa: E402
import io
from PIL import Image

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


class Stations(unittest.TestCase):
    NOW = datetime(2026, 11, 2, 13, 45, tzinfo=ICT)

    def d(self, rt, name, t, tz="UTC", ag="tmd", fn=None):
        return {"radar_type": rt, "radar_name": name, "agency": ag, "timezone": tz, "media_datetime": t,
                "filename": fn or rt + ".jpg", "media_path": "P-" + rt}

    def test_pick_fresh_prefer_120_and_timezones(self):
        data = [self.d("svp120", "เรดาร์สุวรรณภูมิ รัศมี 120 กม.", "2026-11-02 06:40"),
                self.d("svp240", "เรดาร์สุวรรณภูมิ รัศมี 240 กม.", "2026-11-02 06:30"),
                self.d("skm120", "เรดาร์สมุทรสงคราม รัศมี 120 กม.", "2026-05-04 06:40"),   # เก่า → ใช้ 240
                self.d("skm240", "เรดาร์สมุทรสงคราม รัศมี 240 กม.", "2026-11-02 06:30"),
                self.d("njk", "เรดาร์หนองจอก รัศมี 120 กม.", "2026-11-02 13:25", tz="TST", ag="bma"),   # เวลาไทย
                self.d("nan120", "เรดาร์น่าน รัศมี 120 กม.", "", fn="nan120_error.jpg"),
                self.d("ryg240", "เรดาร์ระยอง รัศมี 240 กม.", "2019-03-16 15:15"),
                self.d("xyz", "เรดาร์ไม่รู้จัก รัศมี 120 กม.", "2026-11-02 06:40")]
        p = stations.pick(data, self.NOW)
        self.assertEqual(sorted(p), ["njk", "skm", "svp"])
        self.assertEqual(p["svp"]["type"], "svp120")
        self.assertEqual(p["svp"]["r"], 120)
        self.assertEqual(p["skm"]["type"], "skm240")
        self.assertEqual(p["njk"]["n"], "หนองจอก")
        self.assertEqual(p["njk"]["_t"].strftime("%H:%M"), "13:25")
        self.assertEqual(p["svp"]["_t"].strftime("%H:%M"), "13:40")   # 06:40 UTC = 13:40 น.

    def test_to_jpg_gif_last_frame_and_resize(self):
        frames = [Image.new("RGB", (1000, 800), c) for c in ((255, 0, 0), (0, 0, 255))]
        b = io.BytesIO(); frames[0].save(b, "GIF", save_all=True, append_images=frames[1:])
        jpg, size = stations.to_jpg(b.getvalue())
        self.assertEqual(size, (720, 576))
        px = Image.open(io.BytesIO(jpg)).convert("RGB").getpixel((10, 10))
        self.assertTrue(px[2] > 200 and px[0] < 60, px)   # เฟรมสุดท้าย (น้ำเงิน)


if __name__ == "__main__":
    unittest.main()
