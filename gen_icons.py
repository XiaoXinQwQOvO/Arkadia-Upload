#!/usr/bin/env python3
"""Prepare decrypted IPA for App Store Connect / TestFlight upload.

- Fix LC_ENCRYPTION_INFO_64: cryptid=0, correct cryptoff/cryptsize (90180/90209)
- Remove SC_Info directory (90047)
- Remove UISupportedDevices from Info.plist (90190)
- Bump MinimumOSVersion to 13.0 (90068)
- Generate app icon PNGs in bundle root (90022)
- Build Asset Catalog with actool and replace Assets.car (90023/91111)
- Set CFBundleIconName/CFBundleIcons/CFBundleIcons~ipad in Info.plist (90713)
"""

import os, sys, struct, zlib, plistlib, shutil, json, tempfile, subprocess, time

PAGE_SIZE = 0x4000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SOURCE_ICONS = {
    1024: os.path.join(SCRIPT_DIR, '1024x1024.png'),
    167: os.path.join(SCRIPT_DIR, '167x167.png'),
    152: os.path.join(SCRIPT_DIR, '152x152.png'),
}


def get_icon(px):
    if px in SOURCE_ICONS and os.path.exists(SOURCE_ICONS[px]):
        with open(SOURCE_ICONS[px], 'rb') as f:
            return f.read()
    return make_png(px, px)


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
        if cmd == 0x19:
            segname = data[offset + 8:offset + 24].rstrip(b'\x00').decode('utf-8', errors='replace')
            if segname == '__TEXT':
                text_fileoff = struct.unpack_from('<Q', data, offset + 40)[0]
                text_filesize = struct.unpack_from('<Q', data, offset + 48)[0]
        elif cmd in (0x21, 0x2C):
            enc_offset = offset
        offset += cmdsize
    if enc_offset < 0:
        return
    new_cryptoff = text_fileoff + PAGE_SIZE
    new_cryptsize = min(max(text_filesize - PAGE_SIZE, 0), 0xFFFFFFFF)
    struct.pack_into('<I', data, enc_offset + 8, new_cryptoff)
    struct.pack_into('<I', data, enc_offset + 12, new_cryptsize)
    struct.pack_into('<I', data, enc_offset + 16, 0)
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

    if 'CFBundleVersion' in plist:
        try:
            old_ver = int(str(plist['CFBundleVersion']))
            plist['CFBundleVersion'] = str(old_ver + 1)
            print(f"  Bumped CFBundleVersion: {old_ver} -> {old_ver + 1}")
        except ValueError:
            plist['CFBundleVersion'] = str(int(time.time()))
            print(f"  Set CFBundleVersion: {plist['CFBundleVersion']}")

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
            f.write(get_icon(px))
    print(f"  Generated {len(icons)} icon files")


def build_asset_catalog(app_bundle):
    """Build Assets.car with actool and replace the one in the bundle."""
    tmp = tempfile.mkdtemp(prefix='assetcat_')
    xcassets = os.path.join(tmp, 'Assets.xcassets')
    appiconset = os.path.join(xcassets, 'AppIcon.appiconset')
    os.makedirs(appiconset, exist_ok=True)

    icon_files = {
        'icon-29.png': 29, 'icon-29@2x.png': 58, 'icon-29@3x.png': 87,
        'icon-40.png': 40, 'icon-40@2x.png': 80, 'icon-40@3x.png': 120,
        'icon-60@2x.png': 120, 'icon-60@3x.png': 180,
        'icon-76.png': 76, 'icon-76@2x.png': 152, 'icon-83.5@2x.png': 167,
        'icon-1024.png': 1024,
    }
    for name, px in icon_files.items():
        with open(os.path.join(appiconset, name), 'wb') as f:
            f.write(get_icon(px))

    images = [
        {"filename": "icon-29.png", "idiom": "iphone", "scale": "1x", "size": "29x29"},
        {"filename": "icon-29@2x.png", "idiom": "iphone", "scale": "2x", "size": "29x29"},
        {"filename": "icon-29@3x.png", "idiom": "iphone", "scale": "3x", "size": "29x29"},
        {"filename": "icon-40.png", "idiom": "iphone", "scale": "1x", "size": "40x40"},
        {"filename": "icon-40@2x.png", "idiom": "iphone", "scale": "2x", "size": "40x40"},
        {"filename": "icon-40@3x.png", "idiom": "iphone", "scale": "3x", "size": "40x40"},
        {"filename": "icon-60@2x.png", "idiom": "iphone", "scale": "2x", "size": "60x60"},
        {"filename": "icon-60@3x.png", "idiom": "iphone", "scale": "3x", "size": "60x60"},
        {"filename": "icon-29.png", "idiom": "ipad", "scale": "1x", "size": "29x29"},
        {"filename": "icon-29@2x.png", "idiom": "ipad", "scale": "2x", "size": "29x29"},
        {"filename": "icon-40.png", "idiom": "ipad", "scale": "1x", "size": "40x40"},
        {"filename": "icon-40@2x.png", "idiom": "ipad", "scale": "2x", "size": "40x40"},
        {"filename": "icon-76.png", "idiom": "ipad", "scale": "1x", "size": "76x76"},
        {"filename": "icon-76@2x.png", "idiom": "ipad", "scale": "2x", "size": "76x76"},
        {"filename": "icon-83.5@2x.png", "idiom": "ipad", "scale": "2x", "size": "83.5x83.5"},
        {"filename": "icon-1024.png", "idiom": "ios-marketing", "scale": "1x", "size": "1024x1024"},
    ]
    with open(os.path.join(appiconset, 'Contents.json'), 'w') as f:
        json.dump({"images": images, "info": {"author": "xcode", "version": 1}}, f, indent=2)
    with open(os.path.join(xcassets, 'Contents.json'), 'w') as f:
        json.dump({"info": {"author": "xcode", "version": 1}}, f)

    output_dir = os.path.join(tmp, 'output')
    os.makedirs(output_dir, exist_ok=True)
    partial_plist = os.path.join(tmp, 'partial.plist')

    print("  Compiling Asset Catalog with actool...")
    result = subprocess.run([
        'xcrun', 'actool', xcassets,
        '--compile', output_dir,
        '--platform', 'iphoneos',
        '--minimum-deployment-target', '13.0',
        '--app-icon', 'AppIcon',
        '--output-partial-info-plist', partial_plist,
        '--target-device', 'iphone',
        '--target-device', 'ipad',
        '--warnings', '--errors',
    ], capture_output=True, text=True)

    if result.stdout.strip():
        print(f"  actool stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        print(f"  actool stderr: {result.stderr.strip()}")

    car_path = os.path.join(output_dir, 'Assets.car')
    if os.path.exists(car_path) and os.path.getsize(car_path) > 100:
        dest = os.path.join(app_bundle, 'Assets.car')
        shutil.copy2(car_path, dest)
        print(f"  Replaced Assets.car ({os.path.getsize(dest)} bytes)")
        shutil.rmtree(tmp, ignore_errors=True)
        return True
    else:
        print("  actool did not produce Assets.car")
        shutil.rmtree(tmp, ignore_errors=True)
        return False


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

    print("  Building Asset Catalog...")
    if not build_asset_catalog(app):
        print("  WARNING: Assets.car not replaced, upload may fail with 90023/91111")

    print("Done!")


if __name__ == '__main__':
    main()
