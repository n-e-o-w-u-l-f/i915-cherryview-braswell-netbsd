#!/usr/bin/env python3
"""Reconstruct the exact F25/F26 compile-only source stage on native HP.
Downloads pinned public source, preserves all existing source/boot paths.
No install, boot, firmware or privilege operation.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import tarfile
import urllib.request

NETBSD = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
I915 = "b863e1ef62adf5d9793a84aaa3255c13c5030434"
RTL = "df3bc40086d38dcf0e25628c22c06f8c7674fe3d"
ARCHIVE_SHA256 = "3645aca2c1ac9716558075b7747a98583a8e87435f00ff30c786b4b438dbe15b"
FILES_PCI_BLOB = "a7ac4014311206fdd2e5f5c446a0d72651475fd7"
RTL_FILES = json.loads("[{\"path\":\"sys/dev/pci/rtwn8723be_oem.h\",\"blob\":\"b95a72c40dbc4709e8f70e1b63eb0ea2c226267a\",\"size\":1167},{\"path\":\"sys/dev/pci/rtwn8723be_fw.h\",\"blob\":\"c07192e5ab93b590c72dd6976d38c85420d2e185\",\"size\":852},{\"path\":\"sys/dev/pci/rtwn8723be_tx_desc.c\",\"blob\":\"33c3f4933815d966b0240f13befd711a64cabecf\",\"size\":4940},{\"path\":\"sys/dev/pci/rtwn8723be_os_compat.h\",\"blob\":\"54b3f1110e8592012e36c4647bb3f2a579d72144\",\"size\":622},{\"path\":\"sys/dev/pci/rtwn8723be_h2c_native.c\",\"blob\":\"6671e856ec645ca7451f4e3c9f59c4cd9efeb1dc\",\"size\":4214},{\"path\":\"sys/dev/pci/rtwn8723be_f16_1_dma.c\",\"blob\":\"54552325ad85c5b5e06d3b98b97633cb402f4876\",\"size\":9592},{\"path\":\"sys/dev/pci/rtwn8723be_net80211.c\",\"blob\":\"6b2c0d08d29c56c763b31bf25d81450f15736345\",\"size\":10432},{\"path\":\"sys/dev/pci/rtwn8723be_rf_native.h\",\"blob\":\"f0a3fc415e6461dbcd32a1c30328f7dcfefef15e\",\"size\":496},{\"path\":\"sys/dev/pci/rtwn8723be_pwrseq_data.h\",\"blob\":\"fc817a0f4c7efa5b5d72cb64951b0879ab7fd6ee\",\"size\":5789},{\"path\":\"sys/dev/pci/rtwn8723be.c\",\"blob\":\"f7dbedd5f1dd38692d3c31fbe0e30e08a705a985\",\"size\":7723},{\"path\":\"sys/dev/pci/rtwn8723be_txpwr_pg.c\",\"blob\":\"da0d2d530c858b4a7827191bd12153acadb94ce2\",\"size\":4732},{\"path\":\"sys/dev/pci/rtwn8723be_package.h\",\"blob\":\"514114ef95cabb739e35b00786ad6a021dd9ce60\",\"size\":972},{\"path\":\"sys/dev/pci/rtwn8723be_package.c\",\"blob\":\"34a048b99161a01094df83f3fc575203281242e6\",\"size\":1569},{\"path\":\"sys/dev/pci/rtwn8723be_rx_phy.c\",\"blob\":\"a64668a4e1bd33ec912a0c0c633aeafb4f027d32\",\"size\":2887},{\"path\":\"sys/dev/pci/rtwn8723be_rf_serial.h\",\"blob\":\"819d8ac4df4cb12f9c2d5f373ea28a5615355992\",\"size\":1450},{\"path\":\"sys/dev/pci/rtwn8723be_pwrseq.c\",\"blob\":\"0c2e3d800ad24acd614540ae0fedfb2c983fcd41\",\"size\":5093},{\"path\":\"sys/dev/pci/rtwn8723be_datapath.c\",\"blob\":\"235d2578e23198f0ea5f90c2ab3799abf0c23ed7\",\"size\":4722},{\"path\":\"sys/dev/pci/rtwn8723be_rx_binding.c\",\"blob\":\"764cce7e137999085ebae5e0d0de408e627bac43\",\"size\":2331},{\"path\":\"sys/dev/pci/rtwn8723be_rf_path.h\",\"blob\":\"745972b76c51bd40e6eceb1d56c786efcbde7fb2\",\"size\":624},{\"path\":\"sys/dev/pci/rtwn8723be_netbsd.h\",\"blob\":\"1023ed8ab01badf865d92a130622c8e8fa8172cf\",\"size\":7231},{\"path\":\"sys/dev/pci/rtwn8723be_f16_1.h\",\"blob\":\"1af2911d891ae007cdd90c739e588cba8e8e42e2\",\"size\":13915},{\"path\":\"sys/dev/pci/rtwn8723be_txpwr_pg.h\",\"blob\":\"027c10d3b004677655c673b6f41446d6129640ed\",\"size\":1260},{\"path\":\"sys/dev/pci/rtwn8723be_datapath.h\",\"blob\":\"f1eac9dcf7d25f3162894ba2f086b848a473be6b\",\"size\":1942},{\"path\":\"sys/dev/pci/rtwn8723be_rx_decode.c\",\"blob\":\"3a0bd532a515707e8c6101d15c20b9168d2b4ba8\",\"size\":2308},{\"path\":\"sys/dev/pci/rtwn8723be_rf_native.c\",\"blob\":\"4c6c2c85281174c95769fa4b7cca4f3b480bf8f4\",\"size\":4570},{\"path\":\"sys/dev/pci/rtwn8723be_c2h_native.c\",\"blob\":\"20d7a9deeb788d6bfdbed5d4ab25d903f6c17dca\",\"size\":1163},{\"path\":\"sys/dev/pci/rtwn8723be_linux_state.c\",\"blob\":\"b775418c230f74c549f9cb78aec1ce911a5338d1\",\"size\":10421},{\"path\":\"sys/dev/pci/rtwn8723be_rf_path.c\",\"blob\":\"ac26bf7d60f4d4e7ca64f8f944f1a43fb34e2190\",\"size\":3308},{\"path\":\"sys/dev/pci/rtwn8723be_h2c_native.h\",\"blob\":\"ea336726de65265f00bf62cdd00df268b692a17e\",\"size\":980},{\"path\":\"sys/dev/pci/rtwn8723be_h2c.c\",\"blob\":\"cccd5dc932133577fd28236a0bb5b4dc272ad550\",\"size\":3430},{\"path\":\"sys/dev/pci/rtwn8723be_c2h_native.h\",\"blob\":\"fbb75b410fa51729e336fb72a4ce69924fe5bd42\",\"size\":662},{\"path\":\"sys/dev/pci/rtwn8723be_netbsd.c\",\"blob\":\"9542ec44fddf5861fd815cb065af3b3330306726\",\"size\":62109},{\"path\":\"sys/dev/pci/rtwn8723be_tx_desc.h\",\"blob\":\"c999966e0af17f584370318cd94b2b515b8417e9\",\"size\":2224},{\"path\":\"sys/dev/pci/rtwn8723be_phy_bb_sequence.c\",\"blob\":\"2a372664ecd7cd08ba85709210b9593ed4e6a2ff\",\"size\":1910},{\"path\":\"sys/dev/pci/rtwn8723be_net80211.h\",\"blob\":\"bda97593527614ecbbd143cc7d92f230670be992\",\"size\":2123},{\"path\":\"sys/dev/pci/rtwn8723be_rx_native.h\",\"blob\":\"95b5991d333cc8bc6c75ff5c7e18e095b2076ec2\",\"size\":1048},{\"path\":\"sys/dev/pci/rtwn8723be_phy_exec.h\",\"blob\":\"2c00712efd9a1cb8e5ac7a498f94fab8dca3f7c5\",\"size\":1244},{\"path\":\"sys/dev/pci/rtwn8723be_rx_native.c\",\"blob\":\"1a449bf9b3071ff0e2ea430dc2d9fa6451025026\",\"size\":5776},{\"path\":\"sys/dev/pci/rtwn8723be_c2h.c\",\"blob\":\"e18433f463212fb1f419d8769621e267bfaee8e9\",\"size\":3342},{\"path\":\"sys/dev/pci/rtwn8723be_tx_native.h\",\"blob\":\"18810f839314845768d4098c92e2cb6fd60ad554\",\"size\":1126},{\"path\":\"sys/dev/pci/rtwn8723be_oem.c\",\"blob\":\"cf5e054c5c59d71d670e6d442d2bfad615383afa\",\"size\":497},{\"path\":\"sys/dev/pci/rtwn8723be_native.c\",\"blob\":\"c8cd256913f1a0de436453b0430101700f3271a5\",\"size\":7008},{\"path\":\"sys/dev/pci/rtwn8723be_h2c.h\",\"blob\":\"780d7a3bf065323452c42a957ec318779ee1754a\",\"size\":1698},{\"path\":\"sys/dev/pci/rtwn8723be_pwrseq_plan.h\",\"blob\":\"680f7e99a6c32764ee7ce09d683cd8fbf5341867\",\"size\":3458},{\"path\":\"sys/dev/pci/rtwn8723be_linux_state.h\",\"blob\":\"1e6b5d65cfe1f25dcaefce7c9ec827db9f27d591\",\"size\":3953},{\"path\":\"sys/dev/pci/rtwn8723be_rx_decode.h\",\"blob\":\"0de8611a32334922e2147715de178e1d84d22de1\",\"size\":1642},{\"path\":\"sys/dev/pci/rtwn8723be_fw.c\",\"blob\":\"22d22223c6dfa62eabfd5d33cea8e2bd3f560149\",\"size\":4917},{\"path\":\"sys/dev/pci/rtwn8723be_phy_bb_sequence.h\",\"blob\":\"d3a4155b506ecb0d7a6dd70b8f65c2904727cd22\",\"size\":1410},{\"path\":\"sys/dev/pci/rtwn8723be_rx_binding.h\",\"blob\":\"eb405a3722447563796ffb7d02c9a7b4708bcd5e\",\"size\":786},{\"path\":\"sys/dev/pci/rtwn8723be_rx_phy.h\",\"blob\":\"f3b410ed5289bd9f7f13ee9cdca5f225796899b6\",\"size\":690},{\"path\":\"sys/dev/pci/rtwn8723be_c2h.h\",\"blob\":\"c17a65f4d227bb12777b05d1c69fa01f4dbb1c20\",\"size\":2428},{\"path\":\"sys/dev/pci/rtwn8723be_phy_tables.h\",\"blob\":\"695c43b2da030cb031836c241ce8cd7a924d133c\",\"size\":17853},{\"path\":\"sys/dev/pci/rtwn8723be_rf_serial.c\",\"blob\":\"3efc7aad94e5d35d2899b7b36c9f1c681de3def7\",\"size\":4921},{\"path\":\"sys/dev/pci/rtwn8723be_phy_exec.c\",\"blob\":\"739dadd9c9f6c89e2887ebd3eee5656e49589b87\",\"size\":4799},{\"path\":\"sys/dev/pci/rtwn8723be_tx_native.c\",\"blob\":\"84b1d55719a8b349330d6a925fbf23bf5aa0e78f\",\"size\":7777},{\"path\":\"sys/dev/pci/rtwn8723be_mac_table.h\",\"blob\":\"d5967fc01fc968e76b301c8aed3ca4c7b2fb8667\",\"size\":2741}]")
PCI_ADDITION = "\n# BEGIN RTL8723BE EXPLICIT WIP COMPILATION ONLY\n# $NetBSD$\n#\n# EXPERIMENTAL SOURCE INTEGRATION; NOT a production/full-parity kernel target.\n# Append these entries to the target tree's sys/dev/pci/files.pci in an\n# isolated candidate workspace, place the listed sources at sys/dev/pci/,\n# and select rtwn8723be_native* in an explicit candidate kernel config.\n# The original F8 diagnostic attachment is deliberately not selected here.\n#\n# NetBSD/src baseline: 03d918f6d0e81fa05b8f1160eca0628ad39988a6.\n# Includes only independently present core and portable modules. The staged\n# TX-power PG module is compiler-blocked by a missing <stddef.h>; do NOT\n# silently omit it from the full-port coverage requirement.\n#\ndevice  rtwn8723be_native: ifnet, arp, wlan, firmload\nattach  rtwn8723be_native at pci\nfile    dev/pci/rtwn8723be_native.c        rtwn8723be_native\nfile    dev/pci/rtwn8723be_netbsd.c        rtwn8723be_native\nfile    dev/pci/rtwn8723be_f16_1_dma.c     rtwn8723be_native\nfile    dev/pci/rtwn8723be_fw.c            rtwn8723be_native\nfile    dev/pci/rtwn8723be_linux_state.c   rtwn8723be_native\nfile    dev/pci/rtwn8723be_package.c       rtwn8723be_native\nfile    dev/pci/rtwn8723be_pwrseq.c        rtwn8723be_native\nfile    dev/pci/rtwn8723be_phy_bb_sequence.c rtwn8723be_native\nfile    dev/pci/rtwn8723be_phy_exec.c      rtwn8723be_native\nfile    dev/pci/rtwn8723be_rf_serial.c     rtwn8723be_native\nfile    dev/pci/rtwn8723be_rf_path.c       rtwn8723be_native\nfile    dev/pci/rtwn8723be_rf_native.c     rtwn8723be_native\nfile    dev/pci/rtwn8723be_rx_decode.c     rtwn8723be_native\nfile    dev/pci/rtwn8723be_c2h.c           rtwn8723be_native\nfile    dev/pci/rtwn8723be_c2h_native.c    rtwn8723be_native\nfile    dev/pci/rtwn8723be_rx_binding.c    rtwn8723be_native\nfile    dev/pci/rtwn8723be_rx_phy.c        rtwn8723be_native\nfile    dev/pci/rtwn8723be_rx_native.c     rtwn8723be_native\nfile    dev/pci/rtwn8723be_tx_desc.c       rtwn8723be_native\nfile    dev/pci/rtwn8723be_tx_native.c     rtwn8723be_native\nfile    dev/pci/rtwn8723be_datapath.c       rtwn8723be_native\nfile    dev/pci/rtwn8723be_net80211.c        rtwn8723be_native\nfile    dev/pci/rtwn8723be_oem.c           rtwn8723be_native\n# END RTL8723BE EXPLICIT WIP COMPILATION ONLY\nfile    dev/pci/rtwn8723be_h2c.c           rtwn8723be_native\nfile    dev/pci/rtwn8723be_h2c_native.c    rtwn8723be_native\n"
CONFIG = "# $NetBSD$\n# COMPILATION-ONLY PARTIAL RTL8723BE WIP target. Never boot/install.\ninclude \"arch/amd64/conf/GENERIC\"\nrtwn8723be_native* at pci? dev ? function ?\n"

def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "HP-I915-source-stage/1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True, type=Path)
    a = p.parse_args()
    assert platform.system() == "NetBSD" and platform.release().split(".")[0] == "11"
    assert platform.machine() in ("amd64", "x86_64")
    assert socket.gethostname().split(".")[0] == "hp-tpnw121"
    workspace = a.workspace.resolve()
    assert workspace.parent == Path("/home/andreas/projects")
    assert os.getuid() == 1000 and not workspace.exists()
    workspace.mkdir(mode=0o700)
    status = workspace / "stage-status.json"
    def record(phase, **extra):
        status.write_text(json.dumps({"phase": phase, "pid": os.getpid(),
            "netbsd": NETBSD, "i915": I915, "rtl": RTL, **extra}, indent=2)+"\n")
        print(phase, flush=True)
    try:
        record("DOWNLOADING_NETBSD")
        archive = workspace / "netbsd-pinned.tar.gz"
        with urllib.request.urlopen("https://codeload.github.com/NetBSD/src/tar.gz/"+NETBSD, timeout=90) as response, archive.open("xb") as stream:
            while True:
                chunk=response.read(1024*1024)
                if not chunk: break
                stream.write(chunk)
        with archive.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream,"sha256").hexdigest()
        assert archive_hash == ARCHIVE_SHA256, "NetBSD archive SHA256 mismatch; retain and inspect"
        record("EXTRACTING_VERIFIED_NETBSD", archive_sha256=archive_hash)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(workspace, filter="data")
        source = workspace / ("src-"+NETBSD)
        assert (source/"build.sh").is_file()
        record("VERIFYING_RTL_SOURCE")
        def fetch(row):
            data = get("https://raw.githubusercontent.com/n-e-o-w-u-l-f/rtwn8723be-netbsd/"+RTL+"/src/"+Path(row["path"]).name)
            assert blob(data) == row["blob"], row["path"]
            dest = source / row["path"]
            assert not dest.exists(), "source collision: "+row["path"]
            dest.write_bytes(data)
            return {"path":row["path"],"blob":row["blob"],"sha256":hashlib.sha256(data).hexdigest()}
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts=list(pool.map(fetch, RTL_FILES))
        pci=source/"sys/dev/pci/files.pci"
        original=pci.read_bytes()
        assert blob(original)==FILES_PCI_BLOB
        pci.write_bytes(original+PCI_ADDITION.encode())
        config=source/"sys/arch/amd64/conf/RTWN8723BE_STAGE"
        assert not config.exists()
        config.write_text(CONFIG)
        record("CLONING_PINNED_I915")
        project=workspace/"i915"
        subprocess.run(["git","clone","--no-checkout","https://github.com/n-e-o-w-u-l-f/i915-cherryview-braswell-netbsd.git",str(project)],check=True)
        subprocess.run(["git","-C",str(project),"checkout","--detach",I915],check=True)
        subprocess.run(["git","-C",str(project),"diff","--exit-code"],check=True)
        manifest={"netbsd_archive_sha256":archive_hash,"netbsd_pin":NETBSD,"i915_pin":I915,
            "rtl_pin":RTL,"rtl_files":receipts,"files_pci_original":FILES_PCI_BLOB,
            "files_pci_stage":blob(pci.read_bytes()),"config_blob":blob(config.read_bytes()),
            "scope":"Native F26 eleven-patch compile-only old-RTL-PHY stage; modern bridge and full RTL lifecycle are separate open work."}
        (workspace/"source-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        record("SOURCE_STAGE_READY",source=str(source),project=str(project),rtl_files=len(receipts))
    except BaseException as e:
        record("FAILED",error=type(e).__name__+": "+str(e))
        raise

if __name__ == "__main__":
    main()
