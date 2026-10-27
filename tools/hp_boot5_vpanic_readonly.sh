#!/bin/sh
# F18 NetBSD boot option #5 panic evidence, READ ONLY.
# No mounts, writes, device access, kernel replacement, sysctl changes or reboot.
# On known-good F77: sh tools/hp_boot5_vpanic_readonly.sh
# Offline parser: sh tools/hp_boot5_vpanic_readonly.sh --config boot.cfg
set -u
LC_ALL=C
export LC_ALL

print() { printf '%s\n' "$1"; }

parse_cfg() {
    label=$1
    config=$2
    if [ ! -f "$config" ] || [ -L "$config" ] || [ ! -r "$config" ]; then
        print "$label"_CONFIG=NOT_READABLE_OR_SYMLINK
        return
    fi
    print "$label"_CONFIG=READABLE_SOURCE_NOT_NECESSARILY_ACTIVE
    # Never execute anything from the configuration. NetBSD menu entries are
    # one-based, and boot.cfg "menu" values use LABEL:COMMANDS.
    report=$(awk -v p="$label" '
    BEGIN { n=0; found=0; def="UNKNOWN"; timeout="UNKNOWN" }
    /^default=/ {def=substr($0,9)}
    /^timeout=/ {timeout=substr($0,9)}
    /^menu=/ {
        n++
        if(n != 5) next
        found=1
        line=substr($0,6)
        sep=index(line, ":")
        if(sep==0) {
            print p "_MENU5=INVALID_NO_COLON"
            next
        }
        title=substr(line,1,sep-1)
        all=substr(line,sep+1)
        print p "_MENU5_TITLE=" title
        print p "_MENU5_COMMANDS=" all
        cmdcount=split(all,commands,";")
        for(c=1;c<=cmdcount;c++) {
            command=commands[c]
            sub(/^[[:space:]]*/,"",command)
            if(command !~ /^boot([[:space:]]|$)/) continue
            sub(/^boot/,"",command)
            sub(/^[[:space:]]*/,"",command)
            if(command == "" || substr(command,1,1) == "-") {
                print p "_MENU5_BOOT_IMAGE=netbsd_DEFAULT"
                words_count=split(command,parts,/[[:space:]]+/)
                if(words_count>=2 && parts[1] ~ /^-/ &&
                   parts[2] !~ /^-/ && parts[2] ~ /netbsd/) {
                    print p "_MENU5_WARNING=FILENAME_AFTER_FLAGS_IGNORED"
                }
            } else {
                split(command,parts,/[[:space:]]+/)
                print p "_MENU5_BOOT_IMAGE=" parts[1]
            }
            break
        }
    }
    END {
      print p "_MENUS_TOTAL=" n
      print p "_DEFAULT=" def
      print p "_TIMEOUT=" timeout
      if(found==0) print p "_MENU5=NOT_PRESENT"
    }' "$config")
    printf '%s\n' "$report"
    # A boot-image path alone is not proof of which ESP boot.cfg was used.
    # Only in native mode fingerprint a simple root-level NetBSD image name;
    # never evaluate commands read from boot.cfg or open arbitrary paths.
    if [ "$native_probe" = 1 ]; then
        image=$(printf '%s\n' "$report" | awk -F= '$1 ~ /_MENU5_BOOT_IMAGE$/ {print $2; exit}')
        case "$image" in
            netbsd_DEFAULT) image=netbsd ;;
            netbsd*|/netbsd*) ;;
            '') print "$label"_MENU5_FILE=NO_BOOT_IMAGE ; return ;;
            *) print "$label"_MENU5_FILE=UNRESOLVED_OR_DEVICE_QUALIFIED ; return ;;
        esac
        case "$image" in
            *:*|*..*|*[!a-zA-Z0-9_./-]*)
                print "$label"_MENU5_FILE=UNSAFE_OR_DEVICE_QUALIFIED
                return ;;
            /*) kernel_file=$image ;;
            *) kernel_file=/$image ;;
        esac
        if [ -f "$kernel_file" ] && [ ! -L "$kernel_file" ]; then
            print "$label"_MENU5_FILE=REGULAR_FILE
            if command -v sha256 >/dev/null 2>&1; then
                digest=$(sha256 -q "$kernel_file" 2>/dev/null) || digest=HASH_FAILED
                print "$label"_MENU5_KERNEL_SHA256="$digest"
            fi
        else
            print "$label"_MENU5_FILE=ABSENT_OR_SYMLINK
        fi
    fi
}

native_probe=0

case $# in
    0) ;;
    2)
        if [ "$1" = "--config" ]; then
            print "F18_MODE=OFFLINE_BOOTCFG_PARSE_ONLY"
            parse_cfg "SUPPLIED" "$2"
            print "F18_DONE=READ_ONLY_NO_MUTATIONS"
            exit 0
        fi
        print "F18_ERROR=USAGE"
        exit 2 ;;
    *)
        print "F18_ERROR=USAGE"
        exit 2 ;;
esac

if [ "$(uname -s 2>/dev/null)" != NetBSD ]; then
    print "F18_REFUSED=NOT_NETBSD"
    exit 2
fi
native_probe=1
print "F18_MODE=READ_ONLY_RUNNING_NETBSD"
print "F18_SCOPE=MENU5_PANIC_TRIAGE_NOT_BOOT_AUTHORIZATION"
uname -srm 2>/dev/null || :
uname -v 2>/dev/null || :
for oid in machdep.bootmethod machdep.booted_kernel kern.version; do
    sysctl "$oid" 2>/dev/null || print "SYSCTL_$oid=UNAVAILABLE"
done
parse_cfg "ROOT_BIOS_CANDIDATE" /boot.cfg
# On UEFI the loader can read boot.cfg from the actual EFI System Partition.
# A lookalike within the root filesystem is NOT proof of loader use.
parse_cfg "ROOT_EFI_LOOKALIKE" /EFI/NetBSD/boot.cfg
print "F18_ACTIVE_UEFI_MENU=UNKNOWN_UNTIL_ESP_LOADER_SOURCE_VERIFIED"
print "F18_MOUNT_TABLE_BEGIN"
mount 2>/dev/null || :
print "F18_MOUNT_TABLE_END"
print "F18_KERNEL_FILE_CANDIDATES_BEGIN"
for file in /netbsd /netbsd.v1-f77-linux-efuse-map-20260926 /netbsd.rtwn8723be-f15.1-dma-engine /netbsd-11-i915-rtl-diag; do
    if [ -f "$file" ] && [ ! -L "$file" ]; then
        ls -ld "$file" 2>/dev/null || :
        if command -v sha256 >/dev/null 2>&1; then
            digest=$(sha256 -q "$file" 2>/dev/null) || digest=HASH_FAILED
            printf 'KERNEL_SHA256[%s]=%s\n' "$file" "$digest"
        fi
    fi
done
print "F18_KERNEL_FILE_CANDIDATES_END"
print "F18_CRASH_DIRECTORY_BEGIN"
if [ -d /var/crash ]; then
    ls -lAt /var/crash 2>/dev/null | head -n 18 || :
else
    print "CRASH_DIRECTORY=NOT_PRESENT"
fi
print "F18_CRASH_DIRECTORY_END"
# Current boot logs cannot retroactively prove that an earlier failed kernel
# reached mountroot or userland syslog.
print "F18_PREVIOUS_PANIC_TEXT=NOT_CAPTURED_BY_THIS_LIVE_SYSCTL_PROBE"
print "F18_DONE=READ_ONLY_NO_MUTATIONS"
