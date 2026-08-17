#!/usr/bin/env python3
import struct, zlib, os, sys, plistlib

def make_png(w, h, rgba=(80, 120, 200, 255)):
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    row = b'\x00' + bytes(rgba) * w
    idat = chunk(b'IDAT', zlib.compress(row * h, 9))
    return sig + ihdr + idat + chunk(b'IEND', b'')

def main():
    app = sys.argv[1]
    info_plist = os.path.join(app, 'Info.plist')

    icons = {
        'icon-29.png': 29, 'icon-29@2x.png': 58, 'icon-29@3x.png': 87,
        'icon-40.png': 40, 'icon-40@2x.png': 80, 'icon-40@3x.png': 120,
        'icon-60@2x.png': 120, 'icon-60@3x.png': 180,
        'icon-76.png': 76, 'icon-76@2x.png': 152, 'icon-83.5@2x.png': 167,
        'icon-1024.png': 1024,
    }
    for name, px in icons.items():
        with open(os.path.join(app, name), 'wb') as f:
            f.write(make_png(px, px))

    with open(info_plist, 'rb') as f:
        plist = plistlib.load(f)

    plist['CFBundleIconFiles'] = [
        'icon-29', 'icon-29@2x', 'icon-29@3x',
        'icon-40', 'icon-40@2x', 'icon-40@3x',
        'icon-60@2x', 'icon-60@3x',
        'icon-76', 'icon-76@2x', 'icon-83.5@2x',
        'icon-1024',
    ]

    plist['CFBundleIcons'] = {
        'CFBundlePrimaryIcon': {
            'CFBundleIconFiles': [
                'icon-29', 'icon-29@2x', 'icon-29@3x',
                'icon-40@2x', 'icon-40@3x',
                'icon-60@2x', 'icon-60@3x',
            ],
            'UIPrerenderedIcon': False,
        }
    }

    plist['CFBundleIcons~ipad'] = {
        'CFBundlePrimaryIcon': {
            'CFBundleIconFiles': [
                'icon-29', 'icon-29@2x',
                'icon-40', 'icon-40@2x',
                'icon-76', 'icon-76@2x',
                'icon-83.5@2x',
            ],
            'UIPrerenderedIcon': False,
        }
    }

    with open(info_plist, 'wb') as f:
        plistlib.dump(plist, f)

    print(f'Icons generated and Info.plist updated for {app}')

if __name__ == '__main__':
    main()