# -*- coding: utf-8 -*-
"""카테고리별 상단 배너 동기화.
사용법: 카테고리배너/ 폴더에 '분류번호.jpg' (예: 282.jpg) 넣고 실행.
 → 카페24 업로드 + category-banners.json 생성 (캘린더 JSON과 같은 rihoon-sov/docs 에 푸시).
선택: 카테고리배너/배너링크.txt 에 '282 = https://...' 형식으로 배너 클릭 링크 지정.
"""
import re, json, io, os, base64, hashlib, sys
sys.path.insert(0, 'C:/Users/rihoo/projects/rihoon-keywords')
import cafe24
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, '카테고리배너')
CACHE = os.path.join(DIR, '.업로드캐시.json')
LINKS = os.path.join(DIR, '배너링크.txt')
OUT = os.path.join(BASE, 'docs', 'category-banners.json') if os.path.isdir(os.path.join(BASE, 'docs')) \
      else os.path.join(BASE, 'category-banners.json')


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def upload(path):
    im = Image.open(path)
    b = io.BytesIO()
    im.convert('RGB').save(b, 'JPEG', quality=88, optimize=True, progressive=True)
    p = cafe24.api('POST', '/admin/products/images',
                   {'requests': [{'image': base64.b64encode(b.getvalue()).decode()}]})['images'][0]['path']
    if p.startswith('//'):
        p = 'https:' + p
    elif p.startswith('/'):
        p = 'https://' + cafe24._cfg()['mall'] + '.cafe24.com' + p
    return p


def read_links():
    m = {}
    if os.path.exists(LINKS):
        for ln in open(LINKS, encoding='utf-8'):
            ln = ln.strip()
            if not ln or ln.startswith('#') or '=' not in ln:
                continue
            k, v = ln.split('=', 1)
            m[k.strip()] = v.strip()
    return m


def main():
    os.makedirs(DIR, exist_ok=True)
    cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    links = read_links()
    out = {}
    for fn in sorted(os.listdir(DIR)):
        low = fn.lower()
        if low in ('기본.jpg', '기본.jpeg', '기본.png', 'default.jpg', 'default.jpeg', 'default.png'):
            cate = 'default'  # (미사용) 기본 배너
        elif low in ('라이브.jpg', '라이브.jpeg', '라이브.png', 'live.jpg', 'live.jpeg', 'live.png'):
            cate = 'live'  # 라이브 방송 페이지 상단 배너
        else:
            m = re.match(r'(\d+)\.(jpg|jpeg|png)$', fn, re.I)
            if not m:
                continue
            cate = m.group(1)
        path = os.path.join(DIR, fn)
        key = fn + ':' + md5(path)
        url = cache.get(key)
        if url:
            print('  = 캐시:', fn)
        else:
            print('  ↑ 업로드:', fn)
            url = upload(path)
            cache[key] = url
        out[cate] = {'image': url}
        if cate in links:
            out[cate]['link'] = links[cate]
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    try:
        json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception as e:
        print('  (캐시 저장 생략:', e, ')')
    print('카테고리 배너 %d개 → %s' % (len(out), OUT))
    for k, v in out.items():
        print('  ', k, '→', v['image'][-44:], ('(링크O)' if v.get('link') else ''))


if __name__ == '__main__':
    main()
