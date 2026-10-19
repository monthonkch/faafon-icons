"""วาดแผนที่พื้นหลังโทนมืดให้ตรงกับภาพเรดาร์รวมของกรมอุตุฯ (95–108E, 4–22.5N, Web Mercator)
ออกมา 2 ไฟล์: base_full.png (1800x2644 มีชื่อทุกจังหวัด ใช้ตัดรายภาค) · base_th.png (900x1322 เมืองหลัก)"""
import json, math, os, sys, urllib.request
from PIL import Image, ImageDraw, ImageFont, features
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '../repo')
try:
    from wx.provinces import PROVINCES
except ImportError:
    from provinces import PROVINCES   # ใน repo faafon-icons
SRC = {   # ดาวน์โหลดครั้งแรก (ข้อมูลเปิด: Natural Earth, geoBoundaries CC BY 4.0, ฟอนต์ Sarabun OFL)
    'countries.geojson': 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson',
    'th_adm1.geojson': 'https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/THA/ADM1/geoBoundaries-THA-ADM1_simplified.geojson',
    'Sarabun-Bold.ttf': 'https://raw.githubusercontent.com/google/fonts/main/ofl/sarabun/Sarabun-Bold.ttf',
}
for f, u in SRC.items():
    if not os.path.exists(f):
        urllib.request.urlretrieve(u, f)
if not features.check('raqm'):
    print('WARN: ไม่มี libraqm ตัวอักษรไทยอาจวางผิดตำแหน่ง')

W0, E0, S0, N0 = 95.0, 108.0, 4.0, 22.5
my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
def xy(lon, lat, W, H):
    return ((lon - W0) / (E0 - W0) * W, (my(N0) - my(lat)) / (my(N0) - my(S0)) * H)

PAL = {'dark': ('#0E1218', '#1C1F26', '#252A34', '#3A404D', '#6B7385', '#C9CED8'),
       'light': ('#CFE3F2', '#E9ECEF', '#FBFBF8', '#C9CED6', '#8A93A3', '#2A3342')}
cs = json.load(open('countries.geojson'))
adm = json.load(open('th_adm1.geojson'))

def rings(geom):
    if geom['type'] == 'Polygon':
        return geom['coordinates']
    return [r for p in geom['coordinates'] for r in p]

def draw(W, H, labels, fs, mode='dark'):
    SEA, LAND, TH, PROV, BORDER, INK = PAL[mode]
    im = Image.new('RGB', (W, H), SEA)
    d = ImageDraw.Draw(im)
    near = lambda r: any(W0 - 5 < x < E0 + 5 and S0 - 5 < y < N0 + 5 for x, y in r[::10] or r)
    for f in cs['features']:
        th = f['properties'].get('ADM0_A3') == 'THA'
        for r in rings(f['geometry']):
            if near(r):
                d.polygon([xy(x, y, W, H) for x, y in r], fill=TH if th else LAND)
    for f in adm['features']:
        for r in rings(f['geometry']):
            d.line([xy(x, y, W, H) for x, y in r], fill=PROV, width=max(1, W // 900))
    for f in cs['features']:
        for r in rings(f['geometry']):
            if near(r):
                d.line([xy(x, y, W, H) for x, y in r], fill=BORDER, width=max(1, W // 600))
    font = ImageFont.truetype('Sarabun-Bold.ttf', fs)
    boxes = []
    order = sorted(PROVINCES, key=lambda p: (p[1] not in MAJOR, p[1] != 'กรุงเทพมหานคร'))   # เมืองหลักได้ที่ก่อน
    for reg, name, la, lo in order:
        if labels and name not in labels:
            continue
        x, y = xy(lo, la, W, H)
        r = max(3, fs // 6)
        t = 'กรุงเทพฯ' if name == 'กรุงเทพมหานคร' else name
        bb = d.textbbox((x + r + 3, y), t, font=font, anchor='lm')
        bb = (bb[0] - 4, bb[1] - 2, bb[2] + 4, bb[3] + 2)
        d.ellipse([x - r, y - r, x + r, y + r], fill=INK)
        if any(not (bb[2] < o[0] or bb[0] > o[2] or bb[3] < o[1] or bb[1] > o[3]) for o in boxes):
            continue   # ชื่อซ้อนกัน ข้ามไป (เหลือแค่จุด)
        boxes.append(bb)
        d.text((x + r + 3, y), t, font=font, fill=INK, anchor='lm', stroke_width=max(2, fs // 8), stroke_fill=SEA)
    return im

MAJOR = {'กรุงเทพมหานคร', 'เชียงใหม่', 'เชียงราย', 'พิษณุโลก', 'นครสวรรค์', 'ขอนแก่น', 'อุดรธานี', 'นครราชสีมา', 'อุบลราชธานี',
         'ชลบุรี', 'ระยอง', 'จันทบุรี', 'กาญจนบุรี', 'ประจวบคีรีขันธ์', 'ชุมพร', 'สุราษฎร์ธานี', 'ภูเก็ต', 'นครศรีธรรมราช', 'สงขลา', 'นราธิวาส', 'ตาก', 'น่าน'}
q = lambda im: im.quantize(colors=24, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
for mode, sfx in (('dark', ''), ('light', '_l')):
    q(draw(1800, 2644, None, 20, mode)).save(f'base_full{sfx}.png', optimize=True)
    q(draw(900, 1322, MAJOR, 22, mode)).save(f'base_th{sfx}.png', optimize=True)
print('ok')
