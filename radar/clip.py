"""คลิปเรดาร์ (MP4) จากภาพของกรมอุตุนิยมวิทยา: ย้อนหลัง 1 ชม. + พยากรณ์ 3 ชม. (Radar Image API ของ wxmap.tmd.go.th)

ใช้: python radar/clip.py            → out/clip-th.mp4, clip-bkk.mp4 (+ .jpg ภาพตัวอย่าง) และเพิ่ม "clip" ใน out/latest.json
     python radar/clip.py --test DIR  → ทดสอบด้วยภาพในโฟลเดอร์ (ไม่ต่อเน็ต)
รอบเดิมยังใช้ได้ (ref เท่าเดิม) หรือสร้างไม่สำเร็จ → คัดลอกคลิปเดิมจาก branch radar มาใช้ต่อ
"""
import io, json, os, re, shutil, subprocess, sys, tempfile, urllib.request
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont

API = 'https://wxmap.tmd.go.th/api/radar-images/ref-times'
PREV = 'https://raw.githubusercontent.com/monthonkch/faafon-icons/radar/'
ICT = timezone(timedelta(hours=7))
UA = {'User-Agent': 'faafon-thai-weather-bot (+github.com/monthonkch/faafon-icons)'}
W = 720           # ความกว้างคลิป (สูงตามสัดส่วนภาพ)
FPS, HOLD, FADE = 8, 3, 2      # เฟรมละ 0.5 วิ (ค้าง 3 + ค่อยๆ เปลี่ยน 2)
HOLD_NOW, HOLD_END = 12, 12    # "เวลาล่าสุด" และเฟรมสุดท้ายค้าง 1.5 วิ
PROFILES = {'th': 'thailand', 'bkk': 'bangkok'}
FONT_URL = 'https://raw.githubusercontent.com/google/fonts/main/ofl/sarabun/Sarabun-Bold.ttf'


def get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def ref_ms(t):
    return datetime.strptime(t, '%Y%m%d%H%M%S').replace(tzinfo=ICT)


def pick_ref(data):
    """รอบล่าสุดที่มีพยากรณ์ (≥13 เฟรม) ถ้าไม่เก่ากว่ารอบล่าสุดเกิน 30 นาที"""
    refs = [r for r in data.get('ref_times', []) if (r.get('profiles') or {}).get('thailand', {}).get('png')]
    if not refs:
        return None
    full = next((r for r in refs if len(r['profiles']['thailand']['png']) >= 13), None)
    if not full or ref_ms(refs[0]['ref_time']) - ref_ms(full['ref_time']) > timedelta(minutes=30):
        return None
    return full


def frames_of(ref, prof):
    out = []
    for f in (ref['profiles'].get(prof) or {}).get('png', []):
        m = re.search(r'_ts(\d+)_', f['name'])
        if m and f['url'].startswith('https://wxmap.tmd.go.th/'):
            out.append((datetime.fromtimestamp(int(m.group(1)), ICT), f['url']))
    return sorted(out)


def font(size, here):
    p = os.path.join(here, 'Sarabun-Bold.ttf')
    if not os.path.exists(p):
        try:
            open(p, 'wb').write(get(FONT_URL))
        except Exception:
            return ImageFont.load_default(size=size)
    return ImageFont.truetype(p, size)


def label(im, t, ref, i, n, here):
    """ป้ายเวลาตัวใหญ่ด้านบน + แถบความคืบหน้า (จุด = เวลาล่าสุด)"""
    d = ImageDraw.Draw(im, 'RGBA')
    kind = 'พยากรณ์' if t > ref else 'ล่าสุด' if t == ref else 'ย้อนหลัง'
    col = {'พยากรณ์': (224, 86, 26), 'ล่าสุด': (11, 134, 201), 'ย้อนหลัง': (95, 107, 122)}[kind]
    f1, f2 = font(44, here), font(28, here)
    txt = t.strftime('%H:%M') + ' น.'
    d.rounded_rectangle([16, 16, 16 + 360, 16 + 76], 18, fill=(255, 255, 255, 235))
    d.text((34, 54), txt, font=f1, fill=(24, 32, 44), anchor='lm')
    d.rounded_rectangle([206, 30, 362, 78], 14, fill=col + (255,))
    d.text((284, 54), kind, font=f2, fill=(255, 255, 255), anchor='mm')
    # แถบความคืบหน้า
    x0, x1, y = 16, im.width - 16, 108
    d.rounded_rectangle([x0, y - 5, x1, y + 5], 5, fill=(255, 255, 255, 200))
    d.rounded_rectangle([x0, y - 5, x0 + (x1 - x0) * (i + 1) / n, y + 5], 5, fill=col + (255,))
    return im


def build(frames, ref, out_mp4, out_jpg, here, tmp):
    imgs, size = [], None
    for t, src in frames:
        try:
            im = (Image.open(src) if os.path.exists(src) else Image.open(io.BytesIO(get(src)))).convert('RGB')
        except Exception as ex:
            print('WARN frame', t, ex); continue
        if not size:   # ทุกเฟรมขนาดเดียวกับเฟรมแรก (ภาพของกรมอุตุฯ บางเฟรมขนาดต่างกันเล็กน้อย)
            size = (W, round(im.height * W / im.width / 2) * 2)
        imgs.append((t, im.resize(size, Image.LANCZOS)))
    if len(imgs) < 5:
        raise RuntimeError('เฟรมไม่พอ')
    n = len(imgs)
    seq = []
    for i, (t, im) in enumerate(imgs):
        lab = label(im.copy(), t, ref, i, n, here)
        hold = HOLD_END if i == n - 1 else HOLD_NOW if t == ref else HOLD
        seq += [lab] * hold
        if i < n - 1:
            nxt = label(imgs[i + 1][1].copy(), imgs[i + 1][0], ref, i + 1, n, here)
            seq += [Image.blend(lab, nxt, (k + 1) / (FADE + 1)) for k in range(FADE)]
        if t == ref or (i == 0 and not any(x[0] == ref for x in imgs)):
            lab.save(out_jpg, quality=82, optimize=True)   # ภาพตัวอย่าง = เวลาล่าสุด
    for k, im in enumerate(seq):
        im.save(os.path.join(tmp, f'{k:04d}.png'))
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = 'ffmpeg'
    subprocess.run([exe, '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(tmp, '%04d.png'),
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '30', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out_mp4], check=True)
    return imgs[0][1].size, len(seq) / FPS


def keep_previous(out, meta):
    """ใช้คลิปรอบก่อน (ยังไม่มีรอบใหม่/สร้างไม่สำเร็จ) — ไม่งั้นการ force-push จะลบคลิปทิ้ง"""
    try:
        old = json.loads(get(PREV + 'latest.json')).get('clip')
        if not old:
            return False
        for k in PROFILES:
            if k in old:
                for ext in ('mp4', 'jpg'):
                    open(os.path.join(out, f'clip-{k}.{ext}'), 'wb').write(get(PREV + f'clip-{k}.{ext}'))
        meta['clip'] = old
        return True
    except Exception as ex:
        print('WARN keep previous', ex)
        return False


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, 'out'); os.makedirs(out, exist_ok=True)
    mp = os.path.join(out, 'latest.json')
    meta = json.load(open(mp)) if os.path.exists(mp) else {}
    if '--test' in sys.argv:   # ทดสอบ: โฟลเดอร์ภาพ 17 ไฟล์ เรียงตามชื่อ
        d = sys.argv[sys.argv.index('--test') + 1]
        ref = datetime(2026, 10, 20, 16, 0, tzinfo=ICT)
        files = sorted(os.listdir(d))
        sets = {'th': [(ref + timedelta(minutes=15 * (i - 4)), os.path.join(d, f)) for i, f in enumerate(files)]}
        rt = ref.strftime('%Y%m%d%H%M%S')
    else:
        try:
            r = pick_ref(json.loads(get(API)))
        except Exception as ex:
            print('WARN api', ex); r = None
        if not r:
            print('ไม่มีรอบพยากรณ์ใหม่ ใช้คลิปเดิม' if keep_previous(out, meta) else 'ไม่มีคลิป')
            json.dump(meta, open(mp, 'w'), ensure_ascii=False); return
        rt, ref = r['ref_time'], ref_ms(r['ref_time'])
        try:
            if json.loads(get(PREV + 'latest.json')).get('clip', {}).get('ref') == rt and keep_previous(out, meta):
                print('คลิปรอบเดิม', rt); json.dump(meta, open(mp, 'w'), ensure_ascii=False); return
        except Exception:
            pass
        sets = {k: frames_of(r, p) for k, p in PROFILES.items()}
    clip = {'ref': rt}
    for k, fr in sets.items():
        if len(fr) < 5:
            continue
        tmp = tempfile.mkdtemp()
        try:
            size, sec = build(fr, ref, os.path.join(out, f'clip-{k}.mp4'), os.path.join(out, f'clip-{k}.jpg'), here, tmp)
            clip[k] = {'size': list(size), 'sec': round(sec, 1), 'kb': round(os.path.getsize(os.path.join(out, f'clip-{k}.mp4')) / 1024),
                       'from': fr[0][0].strftime('%H:%M'), 'to': fr[-1][0].strftime('%H:%M')}
            print('clip', k, clip[k])
        except Exception as ex:
            print('WARN clip', k, ex)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if len(clip) > 1:
        meta['clip'] = clip
    elif not keep_previous(out, meta):
        print('ไม่มีคลิป')
    json.dump(meta, open(mp, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
