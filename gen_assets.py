#!/usr/bin/env python3
import struct, zlib, json, os, sys

def make_png(w, h, rgba=(80,120,200,255)):
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    row = b'\x00' + bytes(rgba) * w
    idat = chunk(b'IDAT', zlib.compress(row * h, 9))
    return sig + ihdr + idat + chunk(b'IEND', b'')

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'Assets.xcassets'
    d = os.path.join(out, 'AppIcon.appiconset')
    os.makedirs(d, exist_ok=True)

    icons = {
        'icon-29.png':29,'icon-29@2x.png':58,'icon-29@3x.png':87,
        'icon-40.png':40,'icon-40@2x.png':80,'icon-40@3x.png':120,
        'icon-60@2x.png':120,'icon-60@3x.png':180,
        'icon-76.png':76,'icon-76@2x.png':152,'icon-83.5@2x.png':167,
        'icon-1024.png':1024,
    }
    for n, px in icons.items():
        with open(os.path.join(d, n), 'wb') as f:
            f.write(make_png(px, px))

    images = [
        {'filename':'icon-29.png','idiom':'iphone','scale':'1x','size':'29x29'},
        {'filename':'icon-29@2x.png','idiom':'iphone','scale':'2x','size':'29x29'},
        {'filename':'icon-29@3x.png','idiom':'iphone','scale':'3x','size':'29x29'},
        {'filename':'icon-40.png','idiom':'iphone','scale':'1x','size':'40x40'},
        {'filename':'icon-40@2x.png','idiom':'iphone','scale':'2x','size':'40x40'},
        {'filename':'icon-40@3x.png','idiom':'iphone','scale':'3x','size':'40x40'},
        {'filename':'icon-60@2x.png','idiom':'iphone','scale':'2x','size':'60x60'},
        {'filename':'icon-60@3x.png','idiom':'iphone','scale':'3x','size':'60x60'},
        {'filename':'icon-29.png','idiom':'ipad','scale':'1x','size':'29x29'},
        {'filename':'icon-29@2x.png','idiom':'ipad','scale':'2x','size':'29x29'},
        {'filename':'icon-40.png','idiom':'ipad','scale':'1x','size':'40x40'},
        {'filename':'icon-40@2x.png','idiom':'ipad','scale':'2x','size':'40x40'},
        {'filename':'icon-76.png','idiom':'ipad','scale':'1x','size':'76x76'},
        {'filename':'icon-76@2x.png','idiom':'ipad','scale':'2x','size':'76x76'},
        {'filename':'icon-83.5@2x.png','idiom':'ipad','scale':'2x','size':'83.5x83.5'},
        {'filename':'icon-1024.png','idiom':'ios-marketing','scale':'1x','size':'1024x1024'},
    ]
    with open(os.path.join(d,'Contents.json'),'w') as f:
        json.dump({'images':images,'info':{'author':'xcode','version':1}}, f, indent=2)
    root_contents = os.path.join(out, 'Contents.json')
    if not os.path.exists(root_contents):
        with open(root_contents, 'w') as f:
            json.dump({'info': {'author': 'xcode', 'version': 1}}, f, indent=2)
    print('Asset Catalog ready at ' + out + ' (AppIcon added/replaced)')

if __name__ == '__main__':
    main()
