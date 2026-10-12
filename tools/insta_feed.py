# -*- coding: utf-8 -*-
"""자사몰 메인 인스타그램 미리보기 갱신.
인스타그램(@rihoon) 최근 글 6개 → 3:4 썸네일(docs/insta/) + docs/instagram.json.
토큰은 환경변수 IG_TOKEN(메타 시스템 사용자 토큰, instagram_basic). 깃허브 예약 실행(.github/workflows/insta-feed.yml)이 돌린다.
받아 온 글이 없거나 썸네일을 하나도 못 만들면 기존 파일을 건드리지 않고 실패로 끝난다(메인 영역이 비지 않게)."""
import io, json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from PIL import Image

IG_ID = '17841400794280060'          # @rihoon
PAGES = 'https://rihoon.github.io/rihoon-sov/'
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs')
KST = timezone(timedelta(hours=9))
W, H, N = 600, 800, 6


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()


def thumb(raw):
    """가운데를 3:4로 잘라 600x800 JPEG."""
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    w, h = im.size
    if w * H > h * W:
        nw = h * W // H; im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = w * H // W; im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    out = io.BytesIO(); im.resize((W, H), Image.LANCZOS).save(out, 'JPEG', quality=88)
    return out.getvalue()


def main():
    token = os.environ.get('IG_TOKEN', '').strip()
    if not token:
        sys.exit('IG_TOKEN 이 없습니다(저장소 Secrets 에 등록 필요).')
    q = urllib.parse.urlencode({'fields': 'media_type,media_product_type,permalink,timestamp,thumbnail_url,media_url',
                                'limit': 20, 'access_token': token})
    media = json.loads(get(f'https://graph.facebook.com/v21.0/{IG_ID}/media?{q}'))['data']
    os.makedirs(os.path.join(DOCS, 'insta'), exist_ok=True)
    items = []
    for m in media:
        if len(items) == N:
            break
        code = re.search(r'/(?:p|reel)/([^/]+)/', m.get('permalink', ''))
        src = m.get('thumbnail_url') if m.get('media_type') == 'VIDEO' else m.get('media_url')
        if m.get('media_product_type') not in ('FEED', 'REELS') or not code or not src:
            continue
        name = f'insta/{code.group(1)}.jpg'
        path = os.path.join(DOCS, name)
        if not os.path.exists(path):
            try:
                data = thumb(get(src))
            except Exception as e:      # ponytail: 첫 장이 영상인 묶음 글 등은 건너뜀. 자주 생기면 children 조회 추가
                print('건너뜀', m['permalink'], str(e)[:80]); continue
            open(path, 'wb').write(data)
        day = datetime.strptime(m['timestamp'], '%Y-%m-%dT%H:%M:%S%z').astimezone(KST).strftime('%Y-%m-%d')
        items.append({'img': PAGES + name, 'link': m['permalink'], 'type': m['media_product_type'], 'date': day, 'ratio': '3:4'})
    if not items:
        sys.exit('가져온 글이 없어 기존 파일을 그대로 둡니다.')
    jpath = os.path.join(DOCS, 'instagram.json')
    old = json.load(open(jpath, encoding='utf-8')) if os.path.exists(jpath) else {}
    if old.get('items') == items:
        print('변화 없음', len(items), '개'); return
    json.dump({'handle': 'rihoon', 'url': 'https://www.instagram.com/rihoon/', 'updated': datetime.now(KST).strftime('%Y-%m-%d'),
               'items': items, 'ratio': '3:4'}, open(jpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    keep = {os.path.basename(i['img']) for i in items}
    for f in os.listdir(os.path.join(DOCS, 'insta')):       # 안 쓰는 썸네일 정리
        if f not in keep:
            os.remove(os.path.join(DOCS, 'insta', f))
    print('갱신', len(items), '개 |', items[0]['date'], items[0]['link'])


if __name__ == '__main__':
    main()
