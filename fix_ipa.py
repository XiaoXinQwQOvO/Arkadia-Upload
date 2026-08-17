#!/usr/bin/env python3
"""Fix IPA for App Store Connect / TestFlight upload.

Handles:
- Fix LC_ENCRYPTION_INFO_64: set cryptid=0, correct cryptoff/cryptsize (fixes 90180/90209/90125)
- Remove SC_Info directory (fixes 90047)
- Remove invalid Info.plist keys like UISupportedDevices (fixes 90190)
- Bump MinimumOSVersion to 13.0 (fixes 90068 warning)
- Add CFBundleIconName + CFBundleIcons to Info.plist (fixes 90713)
- Generate icon PNGs in bundle root + compile Asset Catalog (fixes 90022/90023/91111)
"""

import os
import sys
import struct
import zlib
import plistlib
import shutil
import json
import tempfile
import subprocess

PAGE_SIZE = 0x4000  # 16384, arm64 page size


def make_png(width, height, rgba=(80, 120, 200, 255)):
    def chunk(typ, data):
        return struct.pack('>I', len(data)) + typ + data + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    row = b'\x00' + bytes(rgba) * width
    raw = row * height
    idat = chunk(b'IDAT', zlib.compress(raw, 9))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def fix_encryption(path):
    """Fix LC_ENCRYPTION_INFO_64: set cryptid=0 and correct extents from __TEXT segment."""
    with open(path, 'rb') as f:
        data = bytearray(f.read())

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != 0xFEEDFACF:
        print(f"  Not 64-bit Mach-O: {path}")
        return False

    ncmds = struct.unpack_from('<I', data, 16)[0]
    sizeofcmds = struct.unpack_from('<I', data, 20)[0]
    header_size = 32

    text_fileoff = 0
    text_filesize = 0
    enc_offset = -1
    enc_cmdsize = 0

    offset = header_size
    for i in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, offset)
        if cmd == 0x19:  # LC_SEGMENT_64
            segname = data[offset + 8:offset + 24].rstrip(b'\x00').decode('utf-8', errors='replace')
            fileoff = struct.unpack_from('<Q', data, offset + 40)[0]
            filesize = struct.unpack_from('<Q', data, offset + 48)[0]
            if segname == '__TEXT':
                text_fileoff = fileoff
                text_filesize = filesize
                print(f"  __TEXT: fileoff=0x{fileoff:x} filesize=0x{filesize:x}")
        elif cmd in (0x21, 0x2C):
            lc_name = "LC_ENCRYPTION_INFO_64" if cmd == 0x2C else "LC_ENCRYPTION_INFO"
            old_cryptoff = struct.unpack_from('<I', data, offset + 8)[0]
            old_cryptsize = struct.unpack_from('<I', data, offset + 12)[0]
            old_cryptid = struct.unpack_from('<I', data, offset + 16)[0]
            print(f"  {lc_name}: cryptoff=0x{old_cryptoff:x} cryptsize=0x{old_cryptsize:x} cryptid={old_cryptid}")
            enc_offset = offset
            enc_cmdsize = cmdsize
        offset += cmdsize

    if enc_offset < 0:
        print(f"  No encryption LC found, skipping")
        return False

    new_cryptoff = text_fileoff + PAGE_SIZE
    new_cryptsize = text_filesize - PAGE_SIZE
    if new_cryptsize < 0:
        new_cryptsize = 0
    if new_cryptsize > 0xFFFFFFFF:
        new_cryptsize = 0xFFFFFFFF
    new_cryptid = 0

    print(f"  Setting: cryptoff=0x{new_cryptoff:x} cryptsize=0x{new_cryptsize:x} cryptid={new_cryptid}")

    struct.pack_into('<I', data, enc_offset + 8, new_cryptoff)
    struct.pack_into('<I', data, enc_offset + 12, new_cryptsize)
    struct.pack_into('<I', data, enc_offset + 16, new_cryptid)

    with open(path, 'wb') as f:
        f.write(data)
    print(f"  Fixed encryption info in {path}")
    return True


def fix_info_plist(plist_path, app_bundle):
    with open(plist_path, 'rb') as f:
        plist = plistlib.load(f)

    changed = False

    for key in ['UISupportedDevices']:
        if key in plist:
            del plist[key]
            print(f"  Removed {key}")
            changed = True

    if 'MinimumOSVersion' in plist:
        min_ver = str(plist['MinimumOSVersion'])
        try:
            if float(min_ver) < 13.0:
                plist['MinimumOSVersion'] = '13.0'
                print(f"  Bumped MinimumOSVersion: {min_ver} -> 13.0")
                changed = True
        except ValueError:
            pass

    plist['CFBundleIconName'] = 'AppIcon'
    print(f"  Set CFBundleIconName = AppIcon")
    changed = True

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
    plist['CFBundleIconFiles'] = [
        'Icon-120', 'Icon-80', 'Icon-60', 'Icon-40', 'Icon-29',
        'Icon-152', 'Icon-167', 'Icon-76',
    ]
    print(f"  Set CFBundleIcons / CFBundleIcons~ipad / CFBundleIconFiles")
    changed = True

    if changed:
        with open(plist_path, 'wb') as f:
            plistlib.dump(plist, f)

    return changed


def install_icon_files(app_bundle):
    icons = {
        'Icon-1024.png': (1024, 1024),
        'Icon-167.png': (167, 167),
        'Icon-152.png': (152, 152),
        'Icon-120.png': (120, 120),
        'Icon-80.png': (80, 80),
        'Icon-76.png': (76, 76),
        'Icon-60.png': (60, 60),
        'Icon-40.png': (40, 40),
        'Icon-29.png': (29, 29),
    }
    for name, (w, h) in icons.items():
        path = os.path.join(app_bundle, name)
        with open(path, 'wb') as f:
            f.write(make_png(w, h))
        print(f"  Generated {name} ({w}x{h})")


def build_asset_catalog(app_bundle):
    """Build Asset Catalog with ALL explicit icon sizes and replace Assets.car."""
    tmp = tempfile.mkdtemp(prefix='assetcat_')
    xcassets = os.path.join(tmp, 'Assets.xcassets')
    appiconset = os.path.join(xcassets, 'AppIcon.appiconset')
    os.makedirs(appiconset, exist_ok=True)

    icon_files = {
        'icon-29.png': 29,
        'icon-29@2x.png': 58,
        'icon-29@3x.png': 87,
        'icon-40.png': 40,
        'icon-40@2x.png': 80,
        'icon-40@3x.png': 120,
        'icon-60@2x.png': 120,
        'icon-60@3x.png': 180,
        'icon-76.png': 76,
        'icon-76@2x.png': 152,
        'icon-83.5@2x.png': 167,
        'icon-1024.png': 1024,
    }

    for name, px in icon_files.items():
        with open(os.path.join(appiconset, name), 'wb') as f:
            f.write(make_png(px, px))

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

    contents_json = {
        "images": images,
        "info": {"author": "xcode", "version": 1}
    }
    with open(os.path.join(appiconset, 'Contents.json'), 'w') as f:
        json.dump(contents_json, f, indent=2)

    with open(os.path.join(xcassets, 'Contents.json'), 'w') as f:
        json.dump({"info": {"author": "xcode", "version": 1}}, f, indent=2)

    output_dir = os.path.join(tmp, 'output')
    os.makedirs(output_dir, exist_ok=True)

    print("  Compiling Asset Catalog with actool...")
    try:
        result = subprocess.run([
            'xcrun', 'actool',
            '--output-format', 'human-readable-text',
            '--minimum-deployment-target', '13.0',
            '--platform', 'iphoneos',
            '--compile',
            '--output', output_dir,
            xcassets
        ], check=True, capture_output=True, text=True)
        if result.stdout.strip():
            print(f"  actool: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"  actool FAILED: {e.stderr}")
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    except FileNotFoundError:
        print("  actool not available")
        shutil.rmtree(tmp, ignore_errors=True)
        return False

    car_path = os.path.join(output_dir, 'Assets.car')
    if os.path.exists(car_path):
        dest = os.path.join(app_bundle, 'Assets.car')
        shutil.copy2(car_path, dest)
        print(f"  Replaced Assets.car ({os.path.getsize(dest)} bytes)")
        shutil.rmtree(tmp, ignore_errors=True)
        return True
    else:
        print("  Assets.car not found in actool output")
        shutil.rmtree(tmp, ignore_errors=True)
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: fix_ipa.py <app_bundle>")
        sys.exit(1)

    app_bundle = sys.argv[1]
    print(f"Fixing: {app_bundle}")

    sc_info = os.path.join(app_bundle, 'SC_Info')
    if os.path.exists(sc_info):
        shutil.rmtree(sc_info)
        print("Removed SC_Info")

    app_name = os.path.basename(app_bundle)
    if app_name.endswith('.app'):
        app_name = app_name[:-4]
    binary_path = os.path.join(app_bundle, app_name)
    if os.path.exists(binary_path):
        print(f"Fixing Mach-O: {binary_path}")
        fix_encryption(binary_path)
    else:
        for name in os.listdir(app_bundle):
            candidate = os.path.join(app_bundle, name)
            if os.path.isfile(candidate) and not name.startswith('.'):
                try:
                    with open(candidate, 'rb') as f:
                        m = f.read(4)
                    if m == b'\xcf\xfa\xfe\xed':
                        print(f"Fixing Mach-O: {candidate}")
                        fix_encryption(candidate)
                        break
                except Exception:
                    pass

    plist_path = os.path.join(app_bundle, 'Info.plist')
    if os.path.exists(plist_path):
        print("Fixing Info.plist")
        fix_info_plist(plist_path, app_bundle)

    print("Installing icon files in bundle root")
    install_icon_files(app_bundle)

    print("Building Asset Catalog (replacing Assets.car)")
    build_asset_catalog(app_bundle)

    print("Done!")


if __name__ == '__main__':
    main()
