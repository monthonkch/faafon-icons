"""ภาพเรดาร์รวม (radar composite) ของกรมอุตุนิยมวิทยา → ภาพพร้อมแผนที่สำหรับ LINE (ทั้งประเทศ + รายภาค)

ที่มา: https://weather.tmd.go.th/composite/ (PCAPPI 2 กม. ทุก 15 นาที, ภาพโปร่งใส 95–108E 4–22.5N แบบ Web Mercator)
ใช้: python radar.py [--overlay ไฟล์ทดสอบ.png] → out/*.jpg + out/latest.json
"""
import io, json, math, os, re, sys
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from PIL import Image, ImageEnhance

BASE = 'https://weather.tmd.go.th/composite/'
W0, E0, S0, N0 = 95.0, 108.0, 4.0, 22.5
REGIONS = {   # ชื่อไฟล์: (ตะวันตก, ตะวันออก, ใต้, เหนือ)
    'north': (97.2, 101.6, 16.8, 20.6), 'northeast': (101.0, 105.8, 14.0, 18.5), 'central': (98.9, 101.9, 12.9, 17.0),
    'east': (100.4, 103.2, 11.4, 14.6), 'west': (97.9, 100.4, 11.0, 16.8), 'south': (97.4, 102.4, 5.5, 11.6),
}
my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
def px(lon, lat, W, H):
    return (lon - W0) / (E0 - W0) * W, (my(N0) - my(lat)) / (my(N0) - my(S0)) * H

def get(path):
    req = Request(BASE + path, headers={'User-Agent': 'faafon-thai-weather-bot (+github.com/monthonkch/faafon-icons)'})
    with urlopen(req, timeout=60) as r:
        return r.read()

def latest():
    lines = [l for l in get('images_composite.list').decode('utf-8', 'replace').splitlines() if 'overlay=' in l]
    m = re.search(r'"([\d-]+ [\d:]+)".*overlay=([^\s,]*zr/\d+\.png)', lines[-1])
    utc = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M')
    return utc, m.group(2)

STEP = 0.05   # องศา (~5.5 กม.)


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
    if '--overlay' in sys.argv:
        ov = Image.open(sys.argv[sys.argv.index('--overlay') + 1]).convert('RGBA'); utc = datetime(2026, 1, 1)
    else:
        utc, f = latest()
        prev = os.environ.get('PREV_UTC', '').strip()
        if prev == utc.strftime('%Y-%m-%d %H:%M'):
            print('unchanged', prev); return 0
        ov = Image.open(io.BytesIO(get('images/' + f))).convert('RGBA')
    ov0 = ov
    meta = {'utc': utc.strftime('%Y-%m-%d %H:%M'), 'ict': (utc + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M'), 'light': 1}
    for sfx, fsfx in (('', ''), ('-l', '_l')):   # โทนมืด + โทนสว่าง
        base = Image.open(os.path.join(here, f'base_full{fsfx}.png')).convert('RGBA')
        ov = ov0.resize(base.size, Image.BILINEAR)
        a = ov.getchannel('A').point(lambda v: min(255, int(v * 1.15)))   # ฝนเห็นชัดขึ้น
        ov.putalpha(a)
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
    json.dump(rain_grid(ov0), open(os.path.join(out, 'grid.json'), 'w'), separators=(',', ':'))
    meta['grid'] = 1
    json.dump(meta, open(os.path.join(out, 'latest.json'), 'w'), ensure_ascii=False)
    open(os.path.join(out, 'CHANGED'), 'w').write(meta['utc'])
    print(meta['ict'], 'ok')

if __name__ == '__main__':
    main()
