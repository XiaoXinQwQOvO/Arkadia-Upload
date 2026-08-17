#!/usr/bin/env python3
"""Prepare decrypted IPA for App Store Connect / TestFlight upload.

- Fix LC_ENCRYPTION_INFO_64: cryptid=0, correct cryptoff/cryptsize (90180/90209)
- Remove SC_Info directory (90047)
- Remove UISupportedDevices from Info.plist (90190)
- Bump MinimumOSVersion to 13.0 (90068)
- Generate app icon PNGs in bundle root (90022/90023)
- Set CFBundleIconName/CFBundleIcons/CFBundleIcons~ipad in Info.plist (90713)
"""

import os, sys, struct, zlib, plistlib, shutil

PAGE_SIZE = 0x4000


def make_png(w, h, rgba=(80, 120, 200, 255)):
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    row = b'\x00' + bytes(rgba) * w
    idat = chunk(b'IDAT', zlib.compress(row * h, 9))
    return sig + ihdr + idat + chunk(b'IEND', b'')


def fix_encryption(path):
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    if struct.unpack_from('<I', data, 0)[0] != 0xFEEDFACF:
        return
    ncmds = struct.unpack_from('<I', data, 16)[0]
    text_fileoff = text_filesize = 0
    enc_offset = -1
    offset = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, offset)
        if cmd == 0x19:  # LC_SEGMENT_64
            segname = data[offset + 8:offset + 24].rstrip(b'\x00').decode('utf-8', errors='replace')
            if segname == '__TEXT':
                text_fileoff = struct.unpack_from('<Q', data, offset + 40)[0]
                text_filesize = struct.unpack_from('<Q', data, offset + 48)[0]
        elif cmd in (0x21, 0x2C):  # LC_ENCRYPTION_INFO(_64)
            enc_offset = offset
        offset += cmdsize
    if enc_offset < 0:
        return
    new_cryptoff = text_fileoff + PAGE_SIZE
    new_cryptsize = min(max(text_filesize - PAGE_SIZE, 0), 0xFFFFFFFF)
    struct.pack_into('<I', data, enc_offset + 8, new_cryptoff)
    struct.pack_into('<I', data, enc_offset + 12, new_cryptsize)
    struct.pack_into('<I', data, enc_offset + 16, 0)  # cryptid=0
    with open(path, 'wb') as f:
        f.write(data)
    print(f"  Fixed encryption: cryptoff=0x{new_cryptoff:x} cryptsize=0x{new_cryptsize:x} cryptid=0")


def fix_info_plist(plist_path):
    with open(plist_path, 'rb') as f:
        plist = plistlib.load(f)

    for key in ['UISupportedDevices']:
        plist.pop(key, None)

    if 'MinimumOSVersion' in plist:
        try:
            if float(str(plist['MinimumOSVersion'])) < 13.0:
                plist['MinimumOSVersion'] = '13.0'
        except ValueError:
            pass

    plist['CFBundleIconName'] = 'AppIcon'
    plist['CFBundleIconFiles'] = [
        'Icon-120', 'Icon-80', 'Icon-60', 'Icon-40', 'Icon-29',
        'Icon-152', 'Icon-167', 'Icon-76',
    ]
    plist['CFBundleIcons'] = {
        'CFBundlePrimaryIcon': {
            'CFBundleIconFiles': ['Icon-120', 'Icon-80', 'Icon-60', 'Icon-40', 'Icon-29'],
            'CFBundleIconName': 'AppIcon',
        }
    }
    plist['CFBundleIcons~ipad'] = {
        'CFBundlePrimaryIcon': {
            'CFBundleIconFiles': ['Icon-167', 'Icon-152', 'Icon-120', 'Icon-80', 'Icon-76', 'Icon-40', 'Icon-29'],
            'CFBundleIconName': 'AppIcon',
        }
    }

    with open(plist_path, 'wb') as f:
        plistlib.dump(plist, f)
    print("  Fixed Info.plist")


def install_icons(app_bundle):
    icons = {
        'Icon-1024.png': 1024, 'Icon-167.png': 167, 'Icon-152.png': 152,
        'Icon-120.png': 120, 'Icon-80.png': 80, 'Icon-76.png': 76,
        'Icon-60.png': 60, 'Icon-40.png': 40, 'Icon-29.png': 29,
    }
    for name, px in icons.items():
        with open(os.path.join(app_bundle, name), 'wb') as f:
            f.write(make_png(px, px))
    print(f"  Generated {len(icons)} icon files")


def main():
    app = sys.argv[1]
    print(f"Preparing: {app}")

    sc_info = os.path.join(app, 'SC_Info')
    if os.path.exists(sc_info):
        shutil.rmtree(sc_info)
        print("  Removed SC_Info")

    app_name = os.path.basename(app)
    if app_name.endswith('.app'):
        app_name = app_name[:-4]
    binary = os.path.join(app, app_name)
    if os.path.exists(binary):
        print(f"  Fixing Mach-O: {app_name}")
        fix_encryption(binary)

    plist = os.path.join(app, 'Info.plist')
    if os.path.exists(plist):
        fix_info_plist(plist)

    install_icons(app)
    print("Done!")


if __name__ == '__main__':
    main()
