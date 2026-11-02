"""เรดาร์รายสถานี (ภาพสด) จากคลังข้อมูลน้ำแห่งชาติ (สสน.) — กรมอุตุฯ · กรมฝนหลวงฯ · กทม.

ใช้: python radar/stations.py   → out/st-<สถานี>.jpg (กว้าง ≤720) และเพิ่ม "st" ใน out/latest.json
     python radar/stations.py --test DIR → ใช้ไฟล์ radar_img.json + รูปในโฟลเดอร์ (ไม่ต่อเน็ต)
บอทใช้ทำการ์ด "เรดาร์ใกล้คุณ" (สถานีที่ใกล้ผู้ใช้ที่สุด 2–3 แห่ง)
ภาพ GIF/PNG ของบางสถานี → แปลงเป็น JPG (LINE รับเฉพาะ JPG/PNG และภาพเล็กโหลดเร็ว)
"""
import io, json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from PIL import Image

API = 'https://api-v3.thaiwater.net/api/v1/thaiwater30/analyst/radar_img'
IMG = 'https://api-v3.thaiwater.net/api/v1/thaiwater30/shared/image?_csrf=&image='
UA = {'User-Agent': 'faafon-thai-weather-bot (+github.com/monthonkch/faafon-icons)'}
ICT = timezone(timedelta(hours=7))
MAX_AGE = 90      # นาที: เก่ากว่านี้ถือว่าสถานีไม่ทำงาน
W = 720
AGENCY = {'tmd': 'กรมอุตุฯ', 'drraa': 'กรมฝนหลวงฯ', 'bma': 'กทม.'}
# ตำแหน่งสถานีเรดาร์ (โดยประมาณ ±5 กม. ใช้หาสถานีที่ใกล้ผู้ใช้ ไม่ได้วาดบนภาพ)
POS = {
    'cri': (19.95, 99.88), 'lmp': (18.57, 99.04), 'mhs': (19.30, 97.98), 'nan': (18.78, 100.78),
    'phs': (16.78, 100.28), 'phb': (16.43, 101.15), 'kkn': (16.46, 102.79), 'skn': (17.15, 104.13),
    'srn': (14.88, 103.49), 'ubn': (15.25, 104.87), 'chn': (15.18, 100.13), 'svp': (13.69, 100.75),
    'skm': (13.41, 100.00), 'ryg': (12.68, 101.28), 'hhn': (12.57, 99.95), 'cmp': (10.49, 99.19),
    'srt': (9.13, 99.14), 'krb': (8.10, 98.98), 'pkt': (8.13, 98.31), 'stp': (7.20, 100.60), 'nrt': (6.42, 101.82),
    'njk': (13.86, 100.86), 'nkm': (13.71, 100.35),
    'omkoi': (17.80, 98.36), 'inburi': (15.03, 100.33), 'phimai': (15.22, 102.50), 'sattahip': (12.70, 100.99),
    'phanom': (8.85, 98.80), 'rongkwang': (18.34, 100.32), 'rasisalai': (15.34, 104.16), 'banphue': (17.69, 102.47),
    'pathio': (10.84, 99.34), 'takhli': (15.26, 100.30),
}


def get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def site(rt):
    """'svp120' → 'svp' · 'takhli' → 'takhli'"""
    return re.sub(r'\d+$', '', rt)


def when(d):
    """เวลาภาพ → datetime ICT (กรมอุตุฯ/ฝนหลวง = UTC, กทม. = เวลาไทย)"""
    if not d.get('media_datetime'):
        return None
    t = datetime.strptime(d['media_datetime'], '%Y-%m-%d %H:%M')
    return (t.replace(tzinfo=timezone.utc) if d.get('timezone') == 'UTC' else t.replace(tzinfo=ICT)).astimezone(ICT)


def pick(data, now):
    """สถานีที่ภาพสด (≤ MAX_AGE นาที) · สถานีเดียวกันมี 120 และ 240 กม. → ใช้ 120 กม. (ละเอียดกว่า)"""
    best = {}
    for d in data:
        rt, s = d.get('radar_type', ''), site(d.get('radar_type', ''))
        t = when(d)
        if s not in POS or not t or not d.get('media_path') or 'error' in (d.get('filename') or ''):
            continue
        age = (now - t).total_seconds() / 60
        if age > MAX_AGE or age < -15:
            continue
        m = re.search(r'(\d+)\s*กม', d.get('radar_name', ''))
        rng = int(m.group(1)) if m else 240
        cur = best.get(s)
        if not cur or rng < cur['r'] or (rng == cur['r'] and t > cur['_t']):
            best[s] = {'type': rt, 'n': re.sub(r'^เรดาร์|\s*รัศมี.*$', '', d.get('radar_name', s)).strip(),
                       'a': d.get('agency', ''), 'r': rng, '_t': t, '_p': d['media_path']}
    return best


def to_jpg(raw):
    im = Image.open(io.BytesIO(raw))
    if getattr(im, 'n_frames', 1) > 1:     # GIF เคลื่อนไหว: เฟรมสุดท้าย = ล่าสุด
        im.seek(im.n_frames - 1)
    im = im.convert('RGB')
    if im.width > W:
        im = im.resize((W, round(im.height * W / im.width)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, 'JPEG', quality=80, optimize=True, progressive=True)
    return b.getvalue(), im.size


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, 'out'); os.makedirs(out, exist_ok=True)
    mp = os.path.join(out, 'latest.json')
    meta = json.load(open(mp)) if os.path.exists(mp) else {}
    test = sys.argv[sys.argv.index('--test') + 1] if '--test' in sys.argv else None
    now = datetime.now(ICT)
    try:
        data = json.load(open(os.path.join(test, 'radar_img.json'))) if test else json.loads(get(API))
        data = data.get('data', [])
        if test:
            now = max(when(d) for d in data if when(d)) + timedelta(minutes=10)
    except Exception as ex:
        print('WARN stations api', ex); return
    st = {}
    for s, v in sorted(pick(data, now).items()):
        try:
            raw = open(os.path.join(test, v['type'] + '.img'), 'rb').read() if test else get(IMG + v['_p'])
            jpg, size = to_jpg(raw)
        except Exception as ex:
            print('WARN station', v['type'], ex); continue
        open(os.path.join(out, f'st-{s}.jpg'), 'wb').write(jpg)
        la, lo = POS[s]
        st[s] = {'n': v['n'], 'a': AGENCY.get(v['a'], v['a']), 'r': v['r'], 'la': la, 'lo': lo,
                 't': v['_t'].strftime('%Y-%m-%d %H:%M'), 'w': size[0], 'h': size[1], 'kb': round(len(jpg) / 1024)}
    print('stations', len(st), ' '.join(f"{k}:{v['t'][11:]}" for k, v in st.items()))
    if st:
        meta['st'] = st
        json.dump(meta, open(mp, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
