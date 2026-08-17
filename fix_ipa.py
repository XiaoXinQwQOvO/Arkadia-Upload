#!/usr/bin/env python3
"""Fix IPA for App Store Connect / TestFlight upload.

Handles:
- Completely remove LC_ENCRYPTION_INFO_64 load command (fixes 90180/90209)
- Remove SC_Info directory (fixes 90047)
- Remove invalid Info.plist keys like UISupportedDevices (fixes 90190)
- Bump MinimumOSVersion to 13.0 (fixes 90068 warning)
- Build Asset Catalog with 1024x1024 icon and replace Assets.car (fixes 90023/91111)
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


def remove_encryption_lc(path):
    """Completely remove LC_ENCRYPTION_INFO / LC_ENCRYPTION_INFO_64 from Mach-O."""
    with open(path, 'rb') as f:
        data = bytearray(f.read())

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != 0xFEEDFACF:
        print(f"  Not 64-bit Mach-O: {path}")
        return False

    ncmds = struct.unpack_from('<I', data, 16)[0]
    sizeofcmds = struct.unpack_from('<I', data, 20)[0]
    header_size = 32
    lc_region_end = header_size + sizeofcmds

    enc_offset = -1
    enc_cmdsize = 0
    offset = header_size
    for i in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, offset)
        if cmd in (0x21, 0x2C):
            lc_name = "LC_ENCRYPTION_INFO_64" if cmd == 0x2C else "LC_ENCRYPTION_INFO"
            cryptid = struct.unpack_from('<I', data, offset + 16)[0]
            print(f"  Found {lc_name}: cryptid={cryptid} cmdsize={cmdsize} at offset={offset}")
            enc_offset = offset
            enc_cmdsize = cmdsize
            break
        offset += cmdsize

    if enc_offset < 0:
        print(f"  No encryption LC found")
        return False

    total_len = len(data)
    new_len = total_len - enc_cmdsize
    new_data = bytearray(new_len)

    new_data[:enc_offset] = data[:enc_offset]
    new_data[enc_offset:lc_region_end - enc_cmdsize] = data[enc_offset + enc_cmdsize:lc_region_end]
    new_content_start = lc_region_end - enc_cmdsize
    new_data[new_content_start:] = data[lc_region_end:]

    struct.pack_into('<I', new_data, 16, ncmds - 1)
    struct.pack_into('<I', new_data, 20, sizeofcmds - enc_cmdsize)

    new_ncmds = ncmds - 1
    offset = header_size
    for i in range(new_ncmds):
        cmd, cmdsize = struct.unpack_from('<II', new_data, offset)

        if cmd == 0x19:  # LC_SEGMENT_64
            fileoff = struct.unpack_from('<Q', new_data, offset + 40)[0]
            filesize = struct.unpack_from('<Q', new_data, offset + 56)[0]
            if filesize > 0 and fileoff >= lc_region_end:
                struct.pack_into('<Q', new_data, offset + 40, fileoff - enc_cmdsize)
        elif cmd == 0x1:  # LC_SEGMENT
            fileoff = struct.unpack_from('<I', new_data, offset + 8)[0]
            filesize = struct.unpack_from('<I', new_data, offset + 12)[0]
            if filesize > 0 and fileoff >= lc_region_end:
                struct.pack_into('<I', new_data, offset + 8, fileoff - enc_cmdsize)
        elif cmd == 0x1D:  # LC_CODE_SIGNATURE
            val = struct.unpack_from('<I', new_data, offset + 8)[0]
            if val >= lc_region_end:
                struct.pack_into('<I', new_data, offset + 8, val - enc_cmdsize)
        elif cmd in (0x22, 0x80000022):  # LC_DYLD_INFO / LC_DYLD_INFO_ONLY
            for fo in [8, 16, 24, 32, 40]:
                val = struct.unpack_from('<I', new_data, offset + fo)[0]
                if val >= lc_region_end:
                    struct.pack_into('<I', new_data, offset + fo, val - enc_cmdsize)
        elif cmd in (0x26, 0x1E, 0x29, 0x2E, 0x2A):  # various link edit commands
            val = struct.unpack_from('<I', new_data, offset + 8)[0]
            if val >= lc_region_end:
                struct.pack_into('<I', new_data, offset + 8, val - enc_cmdsize)

        offset += cmdsize

    with open(path, 'wb') as f:
        f.write(new_data)
    print(f"  Removed encryption LC, file {total_len} -> {new_len} bytes")
    return True


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

    for key in ['CFBundleIcons', 'CFBundleIcons~ipad', 'CFBundleIconFiles', 'CFBundleIconName']:
        if key in plist:
            del plist[key]
            print(f"  Removed {key} from Info.plist (using Asset Catalog)")
            changed = True

    if changed:
        with open(plist_path, 'wb') as f:
            plistlib.dump(plist, f)

    return changed


def build_asset_catalog(app_bundle):
    """Build a complete AppIcon Asset Catalog and replace Assets.car."""
    tmp = tempfile.mkdtemp(prefix='assetcat_')
    xcassets = os.path.join(tmp, 'Assets.xcassets')
    appiconset = os.path.join(xcassets, 'AppIcon.appiconset')
    os.makedirs(appiconset, exist_ok=True)

    icon_1024_path = os.path.join(appiconset, 'icon-1024.png')
    with open(icon_1024_path, 'wb') as f:
        f.write(make_png(1024, 1024))

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
        print(f"  actool stdout: {result.stdout.strip()}")
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
        remove_encryption_lc(binary_path)
    else:
        for name in os.listdir(app_bundle):
            candidate = os.path.join(app_bundle, name)
            if os.path.isfile(candidate) and not name.startswith('.'):
                try:
                    with open(candidate, 'rb') as f:
                        m = f.read(4)
                    if m == b'\xcf\xfa\xfe\xed':
                        print(f"Fixing Mach-O: {candidate}")
                        remove_encryption_lc(candidate)
                        break
                except Exception:
                    pass

    plist_path = os.path.join(app_bundle, 'Info.plist')
    if os.path.exists(plist_path):
        print("Fixing Info.plist")
        fix_info_plist(plist_path)

    print("Building Asset Catalog (replacing Assets.car)")
    build_asset_catalog(app_bundle)

    print("Done!")


if __name__ == '__main__':
    main()
