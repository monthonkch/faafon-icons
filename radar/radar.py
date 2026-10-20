"""ภาพเรดาร์รวม (radar composite) ของกรมอุตุนิยมวิทยา → ภาพพร้อมแผนที่สำหรับ LINE (ทั้งประเทศ + รายภาค)

ที่มา: https://weather.tmd.go.th/composite/ (PCAPPI 2 กม. ทุก 15 นาที, ภาพโปร่งใส 95–108E 4–22.5N แบบ Web Mercator)
ใช้: python radar.py [--overlay ไฟล์ทดสอบ.png] → out/*.jpg + out/latest.json
"""
import io, json, math, os, re, sys
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

BASE = 'https://weather.tmd.go.th/composite/'
W0, E0, S0, N0 = 95.0, 108.0, 4.0, 22.5
REGIONS = {   # ชื่อไฟล์: (ตะวันตก, ตะวันออก, ใต้, เหนือ)
    'north': (97.2, 101.6, 16.8, 20.6), 'northeast': (101.0, 105.8, 14.0, 18.5), 'central': (98.9, 101.9, 12.9, 17.0),
    'east': (100.4, 103.2, 11.4, 14.6), 'west': (97.9, 100.4, 11.0, 16.8), 'south': (97.4, 102.4, 5.5, 11.6),
}
my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
def px(lon, lat, W, H):
    return (lon - W0) / (E0 - W0) * W, (my(N0) - my(lat)) / (my(N0) - my(S0)) * H

def vivid(ov, size, light):
    """สีฝนเข้มและทึบขึ้นให้เห็นชัดบนแผนที่ (สีเดิมของกรมอุตุฯ ซีดและโปร่ง): อิ่มสี ×1.5 · ทึบ ×2 · โทนสว่างกดความสว่างลงนิด"""
    ov = ov.resize(size, Image.BILINEAR)
    a = ov.getchannel('A').point(lambda v: 0 if v < 8 else min(255, int(v * 2.0) + 40))
    rgb = ImageEnhance.Color(ov.convert('RGB')).enhance(1.5)
    if light:
        rgb = ImageEnhance.Brightness(rgb).enhance(0.85)
    rgb.putalpha(a)
    return rgb


def get(path):
    req = Request(BASE + path, headers={'User-Agent': 'faafon-thai-weather-bot (+github.com/monthonkch/faafon-icons)'})
    with urlopen(req, timeout=60) as r:
        return r.read()

def frame_list():
    """[(เวลา UTC, ไฟล์ภาพ)] เรียงเก่า→ใหม่ จาก images_composite.list"""
    out = []
    for l in get('images_composite.list').decode('utf-8', 'replace').splitlines():
        m = re.search(r'"([\d-]+ [\d:]+)".*overlay=([^\s,]*zr/\d+\.png)', l)
        if m:
            out.append((datetime.strptime(m.group(1), '%Y-%m-%d %H:%M'), m.group(2)))
    return out


def latest():
    return frame_list()[-1]


ANIM_FRAMES, ANIM_MAX_PX, ANIM_KB = 8, 480, 290   # 2 ชม. ล่าสุด · LINE: ภาพเคลื่อนไหว (APNG) ≤ 300 KB


def animate(here, out, frames, meta):
    """ภาพเคลื่อนไหว APNG ต่อภาค/ทั้งประเทศ ทั้งสองโทน: <ภาพ>[-l]-anim.png · เฟรมสุดท้ายค้างนานขึ้น"""
    try:
        font = ImageFont.load_default(size=28)
    except Exception:
        font = ImageFont.load_default()
    boxes = {'th': (W0, E0, S0, N0)}; boxes.update(REGIONS)
    for sfx, fsfx in (('', ''), ('-l', '_l')):
        base = Image.open(os.path.join(here, f'base_full{fsfx}.png')).convert('RGBA')
        W, H = base.size
        fulls = []
        for utc, ov in frames:
            ov = vivid(ov, base.size, bool(sfx))
            fulls.append((utc, Image.alpha_composite(base, ov).convert('RGB')))
        ink, bg = ('#FFFFFF', '#000000A0') if not sfx else ('#18202C', '#FFFFFFC0')
        for k, (w, e, s, n) in boxes.items():
            x0, y0 = px(w, n, W, H); x1, y1 = px(e, s, W, H)
            size = None
            for px_max, nf in ((ANIM_MAX_PX, len(fulls)), (400, len(fulls)), (360, min(6, len(fulls))), (300, min(5, len(fulls)))):
                imgs = []
                for utc, full in fulls[-nf:]:
                    im = full.crop((round(x0), round(y0), round(x1), round(y1)))
                    sc = min(1, px_max / max(im.size)); im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
                    d = ImageDraw.Draw(im, 'RGBA')
                    t = (utc + timedelta(hours=7)).strftime('%H:%M')
                    d.rounded_rectangle([8, 8, 8 + 18 * len(t) + 16, 48], 10, fill=bg)
                    d.text((16, 28), t, font=font, fill=ink, anchor='lm')
                    imgs.append(im.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
                bio = io.BytesIO()
                dur = [500] * (len(imgs) - 1) + [1500]
                imgs[0].save(bio, format='PNG', save_all=True, append_images=imgs[1:], duration=dur, loop=0, optimize=True)
                if bio.tell() <= ANIM_KB * 1024:
                    break
            open(os.path.join(out, f'{k}{sfx}-anim.png'), 'wb').write(bio.getvalue())
            meta.setdefault('anim', {})[k] = list(imgs[0].size)
            meta['anim_kb'] = max(meta.get('anim_kb', 0), round(bio.tell() / 1024))
    meta['anim_n'] = len(frames)

STEP = 0.05   # องศา (~5.5 กม.)


TILE = 40   # ช่องต่อด้านของกระเบื้องคำนวณทิศเคลื่อนที่ (2° ≈ 220 กม.)
MAXS = 8    # เลื่อนได้ไม่เกิน ±8 ช่อง ต่อช่วงเวลาที่เทียบ (~44 กม.)


def cells_of(grid):
    """สตริง cells → {(แถว, คอลัมน์): ระดับ}"""
    cs = grid["cells"]
    return {(int(cs[i:i + 3]), int(cs[i + 3:i + 6])): int(cs[i + 6]) for i in range(0, len(cs), 7)}


def _best_shift(prev, cur):
    """หา (dr, dc) ที่ทำให้ฝนเฟรมก่อนเลื่อนไปทับฝนเฟรมนี้ได้มากสุด → (dr, dc, สัดส่วนทับ 0–1)"""
    if len(cur) < 25 or len(prev) < 25:
        return None
    best = (0, 0, -1.0)
    for dr in range(-MAXS, MAXS + 1):
        for dc in range(-MAXS, MAXS + 1):
            hit = sum(1 for (r, c) in prev if (r + dr, c + dc) in cur)
            sc = hit / max(len(cur), len(prev))
            if sc > best[2] or (sc == best[2] and abs(dr) + abs(dc) < abs(best[0]) + abs(best[1])):
                best = (dr, dc, sc)
    return best


def motion(prev_grid, cur_grid, dt):
    """ทิศและความเร็วกลุ่มฝน (เทียบ 2 เฟรมห่าง dt นาที) ทั้งประเทศ + รายกระเบื้อง 40×40 ช่อง
    ใช้พยากรณ์ระยะสั้น (nowcast) ใน Code.gs: ฝนที่จุดนี้ในอีก t นาที ≈ ฝนตอนนี้ที่ตำแหน่ง (จุด − ความเร็ว×t)"""
    prev, cur = set(cells_of(prev_grid)), set(cells_of(cur_grid))
    out = {"dt": dt, "g": None, "tiles": {}}
    g = _best_shift(prev, cur)
    if g:
        out["g"] = [g[0], g[1], round(g[2], 2)]
    tiles = {}
    for (r, c) in cur:
        tiles.setdefault((r // TILE, c // TILE), set()).add((r, c))
    for (tr, tc), cc in tiles.items():
        r0, r1, c0, c1 = tr * TILE - MAXS, (tr + 1) * TILE + MAXS, tc * TILE - MAXS, (tc + 1) * TILE + MAXS
        pp = {(r, c) for (r, c) in prev if r0 <= r < r1 and c0 <= c < c1}
        b = _best_shift(pp, cc)
        if b and b[2] >= 0.3:
            out["tiles"][f"{tr},{tc}"] = [b[0], b[1], round(b[2], 2)]
    return out


def rain_grid(ov):
    """ระดับฝนรายช่อง 0.05° จากสีของภาพเรดาร์ (1 เบา·เขียว, 2 ปานกลาง·เหลือง, 3 หนัก·ส้ม, 4 หนักมาก·แดง/ม่วง)
    เก็บเฉพาะช่องที่มีฝน: สตริง 7 ตัวต่อช่อง = แถว(3) คอลัมน์(3) ระดับ(1) นับจากมุมบนซ้าย 22.5N 95E"""
    W, H = ov.size
    hsv, alpha = ov.convert('RGB').convert('HSV').load(), ov.getchannel('A').load()
    def lv(x, y):
        if alpha[x, y] < 60:
            return 0
        h = hsv[x, y][0] * 360 / 255
        return 1 if 70 <= h < 300 else 2 if h >= 48 else 3 if h >= 20 else 4 if h < 20 or h >= 300 else 1
    rows, cols, cells = round((N0 - S0) / STEP), round((E0 - W0) / STEP), []
    for r in range(rows):
        for c in range(cols):
            best = 0
            for dy in (0.25, 0.5, 0.75):
                for dx in (0.25, 0.5, 0.75):
                    x, y = px(W0 + (c + dx) * STEP, N0 - (r + dy) * STEP, W, H)
                    xi, yi = min(W - 1, int(x)), min(H - 1, int(y))
                    best = max(best, lv(xi, yi))
            if best:
                cells.append(f'{r:03d}{c:03d}{best}')
    return {'step': STEP, 'n': N0, 'w': W0, 'cells': ''.join(cells)}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, 'out'); os.makedirs(out, exist_ok=True)
    if '--overlay' in sys.argv:   # ทดสอบ: เลื่อนภาพเดียวให้เป็นหลายเฟรม
        ov = Image.open(sys.argv[sys.argv.index('--overlay') + 1]).convert('RGBA'); utc = datetime(2026, 1, 1)
        frames = [(utc - timedelta(minutes=15 * (7 - i)), ov.transform(ov.size, Image.AFFINE, (1, 0, 6 * (7 - i), 0, 1, 0))) for i in range(8)]
    else:
        fl = frame_list(); utc, f = fl[-1]
        prev = os.environ.get('PREV_UTC', '').strip()
        if prev == utc.strftime('%Y-%m-%d %H:%M'):
            print('unchanged', prev); return 0
        frames = []
        for t, fn in fl[-ANIM_FRAMES:]:
            try:
                frames.append((t, Image.open(io.BytesIO(get('images/' + fn))).convert('RGBA')))
            except Exception as ex:
                print('WARN frame', fn, ex)
        ov = frames[-1][1] if frames and frames[-1][0] == utc else Image.open(io.BytesIO(get('images/' + f))).convert('RGBA')
    ov0 = ov
    meta = {'utc': utc.strftime('%Y-%m-%d %H:%M'), 'ict': (utc + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M'), 'light': 1}
    for sfx, fsfx in (('', ''), ('-l', '_l')):   # โทนมืด + โทนสว่าง
        base = Image.open(os.path.join(here, f'base_full{fsfx}.png')).convert('RGBA')
        ov = vivid(ov0, base.size, bool(sfx))   # ฝนเห็นชัดขึ้น
        full = Image.alpha_composite(base, ov).convert('RGB')
        th = Image.alpha_composite(Image.open(os.path.join(here, f'base_th{fsfx}.png')).convert('RGBA'), ov.resize((900, 1322), Image.BILINEAR)).convert('RGB')
        th = th.resize((696, 1022), Image.LANCZOS)   # LINE: ภาพไม่เกิน 1024 px
        th.save(os.path.join(out, f'th{sfx}.jpg'), quality=82, optimize=True)
        meta['th'] = {'bbox': [W0, E0, S0, N0], 'size': list(th.size)}
        W, H = full.size
        for k, (w, e, s, n) in REGIONS.items():
            x0, y0 = px(w, n, W, H); x1, y1 = px(e, s, W, H)
            im = full.crop((round(x0), round(y0), round(x1), round(y1)))
            if max(im.size) > 1024:
                im = im.resize((round(im.width * 1024 / max(im.size)), round(im.height * 1024 / max(im.size))), Image.LANCZOS)
            im = ImageEnhance.Sharpness(im).enhance(1.1)
            im.save(os.path.join(out, f'{k}{sfx}.jpg'), quality=82, optimize=True)
            meta[k] = {'bbox': [w, e, s, n], 'size': list(im.size)}
    grid = rain_grid(ov0)
    # ทิศทางกลุ่มฝน: เทียบกับเฟรมราว 30 นาทีก่อน (ถ้ามี)
    try:
        old = [(t, im) for t, im in frames if 20 <= (utc - t).total_seconds() / 60 <= 45]
        if old:
            t1, im1 = min(old, key=lambda x: abs((utc - x[0]).total_seconds() / 60 - 30))
            grid["mv"] = motion(rain_grid(im1), grid, round((utc - t1).total_seconds() / 60))
            print('motion', grid["mv"]["dt"], 'นาที', grid["mv"]["g"], len(grid["mv"]["tiles"]), 'กระเบื้อง')
    except Exception as ex:
        print('WARN motion', ex)
    json.dump(grid, open(os.path.join(out, 'grid.json'), 'w'), separators=(',', ':'))
    if len(frames) >= 3:
        try:
            animate(here, out, frames, meta)
        except Exception as ex:   # ภาพเคลื่อนไหวล้ม ภาพนิ่งยังใช้ได้
            print('WARN animate', ex)
    meta['grid'] = 1
    json.dump(meta, open(os.path.join(out, 'latest.json'), 'w'), ensure_ascii=False)
    open(os.path.join(out, 'CHANGED'), 'w').write(meta['utc'])
    print(meta['ict'], 'ok')

if __name__ == '__main__':
    main()
