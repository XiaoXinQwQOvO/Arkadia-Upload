#!/usr/bin/env python3
"""Fix IPA for App Store Connect / TestFlight upload.

Handles:
- Set LC_ENCRYPTION_INFO_64 cryptid=0 and zero extents (fixes 90180/90209)
- Remove SC_Info directory (fixes 90047)
- Remove invalid Info.plist keys like UISupportedDevices (fixes 90190)
- Bump MinimumOSVersion to 13.0 (fixes 90068 warning)
- Generate and install missing app icons (fixes 90023/91111)
"""

import os
import sys
import struct
import zlib
import plistlib
import shutil


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


def fix_macho(path):
    with open(path, 'rb') as f:
        data = bytearray(f.read())

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != 0xFEEDFACF:
        print(f"  Not 64-bit Mach-O: {path}")
        return False

    ncmds = struct.unpack_from('<I', data, 16)[0]
    sizeofcmds = struct.unpack_from('<I', data, 20)[0]
    header_size = 32

    offset = header_size
    fixed = False

    for i in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, offset)
        if cmd in (0x21, 0x2C):
            lc_name = "LC_ENCRYPTION_INFO_64" if cmd == 0x2C else "LC_ENCRYPTION_INFO"
            cryptoff = struct.unpack_from('<I', data, offset + 8)[0]
            cryptsize = struct.unpack_from('<I', data, offset + 12)[0]
            cryptid = struct.unpack_from('<I', data, offset + 16)[0]
            print(f"  {lc_name}: cryptoff={cryptoff} cryptsize={cryptsize} cryptid={cryptid}")
            struct.pack_into('<I', data, offset + 8, 0)
            struct.pack_into('<I', data, offset + 12, 0)
            struct.pack_into('<I', data, offset + 16, 0)
            fixed = True
            print(f"  -> Zeroed cryptoff, cryptsize, cryptid")
        offset += cmdsize

    if fixed:
        with open(path, 'wb') as f:
            f.write(data)
        print(f"  Fixed Mach-O: {path}")

    return fixed


def fix_info_plist(plist_path):
    with open(plist_path, 'rb') as f:
        plist = plistlib.load(f)

    changed = False

    for key in ['UISupportedDevices']:
        if key in plist:
            del plist[key]
            print(f"  Removed {key} from Info.plist")
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

    if changed:
        with open(plist_path, 'wb') as f:
            plistlib.dump(plist, f)

    return changed


def install_icons(app_bundle):
    plist_path = os.path.join(app_bundle, 'Info.plist')
    with open(plist_path, 'rb') as f:
        plist = plistlib.load(f)

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
        if not os.path.exists(path):
            with open(path, 'wb') as f:
                f.write(make_png(w, h))
            print(f"  Generated {name} ({w}x{h})")

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
    plist['CFBundleIconFiles'] = ['Icon-120', 'Icon-80', 'Icon-60', 'Icon-40', 'Icon-29']

    with open(plist_path, 'wb') as f:
        plistlib.dump(plist, f)
    print("  Updated Info.plist with icon references")


def build_asset_catalog(app_bundle):
    import tempfile
    import subprocess

    icon_1024 = os.path.join(app_bundle, 'Icon-1024.png')
    if not os.path.exists(icon_1024):
        return

    tmp = tempfile.mkdtemp(prefix='assetcat_')
    xcassets = os.path.join(tmp, 'Assets.xcassets')
    appiconset = os.path.join(xcassets, 'AppIcon.appiconset')
    os.makedirs(appiconset, exist_ok=True)

    shutil.copy2(icon_1024, os.path.join(appiconset, 'icon-1024.png'))

    contents_json = {
        "images": [
            {
                "filename": "icon-1024.png",
                "idiom": "universal",
                "platform": "ios",
                "size": "1024x1024"
            }
        ],
        "info": {"author": "xcode", "version": 1}
    }
    import json
    with open(os.path.join(appiconset, 'Contents.json'), 'w') as f:
        json.dump(contents_json, f)

    with open(os.path.join(xcassets, 'Contents.json'), 'w') as f:
        json.dump({"info": {"author": "xcode", "version": 1}}, f)

    output_dir = os.path.join(tmp, 'output')
    os.makedirs(output_dir, exist_ok=True)

    try:
        subprocess.run([
            'xcrun', 'actool',
            '--output-format', 'human-readable-text',
            '--minimum-deployment-target', '13.0',
            '--platform', 'iphoneos',
            '--compile',
            '--output', output_dir,
            xcassets
        ], check=True, capture_output=True, text=True)

        car_path = os.path.join(output_dir, 'Assets.car')
        if os.path.exists(car_path):
            existing_car = os.path.join(app_bundle, 'Assets.car')
            if not os.path.exists(existing_car):
                shutil.copy2(car_path, existing_car)
                print("  Installed Assets.car with 1024x1024 icon")
            else:
                print("  Assets.car already exists, skipping (Info.plist icons will be used)")
    except subprocess.CalledProcessError as e:
        print(f"  actool failed: {e.stderr}")
    except FileNotFoundError:
        print("  actool not available, skipping Asset Catalog")

    shutil.rmtree(tmp, ignore_errors=True)


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
        fix_macho(binary_path)
    else:
        for name in os.listdir(app_bundle):
            candidate = os.path.join(app_bundle, name)
            if os.path.isfile(candidate) and not name.startswith('.'):
                try:
                    with open(candidate, 'rb') as f:
                        m = f.read(4)
                    if m == b'\xcf\xfa\xfe\xed':
                        print(f"Fixing Mach-O: {candidate}")
                        fix_macho(candidate)
                        break
                except Exception:
                    pass

    plist_path = os.path.join(app_bundle, 'Info.plist')
    if os.path.exists(plist_path):
        print("Fixing Info.plist")
        fix_info_plist(plist_path)

    print("Installing icons")
    install_icons(app_bundle)

    print("Building Asset Catalog for 1024x1024 icon")
    build_asset_catalog(app_bundle)

    print("Done!")


if __name__ == '__main__':
    main()