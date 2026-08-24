#!/usr/bin/env bash
# ==============================================================================
# Void-Builder QEMU Runner Script
# Tests generated Void Linux ISOs under QEMU with BIOS/UEFI, KVM and custom graphics.
# ==============================================================================

set -e

# Default settings
DEFAULT_RAM="2048M"
DEFAULT_SMP="2"
DEFAULT_VGA="std"     # std is standard VGA (maximum compatibility)
DEFAULT_BIOS="bios"   # bios or uefi
ISO_FILE=""
RAM="${DEFAULT_RAM}"
SMP="${DEFAULT_SMP}"
VGA="${DEFAULT_VGA}"
BOOT_MODE="${DEFAULT_BIOS}"
ENABLE_KVM=true
SERIAL_DEBUG=false

# Colors for terminal output
BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
RED="\033[1;31m"
RESET="\033[0m"

# Print banner
print_banner() {
    echo -e "${BLUE}==============================================================================${RESET}"
    echo -e "${BOLD} Void-Builder: QEMU ISO Test Runner${RESET}"
    echo -e "${BLUE}==============================================================================${RESET}"
}

# Print usage
usage() {
    print_banner
    echo -e "Usage: $0 [options] [path_to_iso]"
    echo ""
    echo "Options:"
    echo "  -i, --iso <file>       Specify ISO path (defaults to newest in output/)"
    echo "  -m, --ram <size>       RAM size (default: 2048M, e.g. 4096M, 4G)"
    echo "  -c, --smp <cores>      Number of CPU cores (default: 2)"
    echo "  -v, --vga <type>       Graphics adapter: std (default/compatible), virtio, qxl, vmware"
    echo "  -u, --uefi             Boot with UEFI (OVMF) instead of Legacy BIOS"
    echo "  -s, --serial           Attach serial console to current terminal (captures early boot)"
    echo "  --no-kvm               Disable KVM acceleration"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                      # Boot newest ISO with Standard VGA"
    echo "  $0 -v virtio                            # Boot with VirtIO GPU driver"
    echo "  $0 -s                                   # Boot and redirect serial to terminal"
    echo "  $0 -u                                   # Boot with UEFI"
    echo "  $0 -m 4G -c 4                           # Boot with 4GB RAM and 4 CPU cores"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--iso)
            ISO_FILE="$2"
            shift 2
            ;;
        -m|--ram)
            RAM="$2"
            shift 2
            ;;
        -c|--smp)
            SMP="$2"
            shift 2
            ;;
        -v|--vga)
            VGA="$2"
            shift 2
            ;;
        -u|--uefi)
            BOOT_MODE="uefi"
            shift
            ;;
        -s|--serial)
            SERIAL_DEBUG=true
            shift
            ;;
        --no-kvm)
            ENABLE_KVM=false
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            if [[ -z "$ISO_FILE" && "$1" != -* ]]; then
                ISO_FILE="$1"
                shift
            else
                echo -e "${RED}Unknown option: $1${RESET}"
                usage
            fi
            ;;
    esac
done

print_banner

# Auto-detect ISO if not provided
if [[ -z "$ISO_FILE" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    OUTPUT_DIR="${SCRIPT_DIR}/output"

    if [[ -d "$OUTPUT_DIR" ]]; then
        ISO_FILE=$(ls -t "${OUTPUT_DIR}"/*.iso 2>/dev/null | head -n 1 || true)
    fi
fi

if [[ -z "$ISO_FILE" || ! -f "$ISO_FILE" ]]; then
    echo -e "${RED}Error: No ISO file found or specified!${RESET}"
    echo "Please provide an ISO file path or compile one first."
    exit 1
fi

echo -e "${GREEN}Using ISO:${RESET}  ${BOLD}${ISO_FILE}${RESET}"
echo -e "${GREEN}Memory:${RESET}    ${RAM}"
echo -e "${GREEN}CPU Cores:${RESET} ${SMP}"
echo -e "${GREEN}Graphics:${RESET}  ${VGA}"
echo -e "${GREEN}Boot Mode:${RESET} ${BOOT_MODE^^}"

# Check QEMU binary
QEMU_BIN="qemu-system-x86_64"
if ! command -v "$QEMU_BIN" >/dev/null 2>&1; then
    echo -e "${RED}Error: '$QEMU_BIN' is not installed on this system.${RESET}"
    exit 1
fi

# Build QEMU command arguments
QEMU_ARGS=(
    "-m" "$RAM"
    "-smp" "$SMP"
    "-cdrom" "$ISO_FILE"
    "-boot" "d"
    "-vga" "$VGA"
    "-display" "gtk"
    "-net" "nic,model=virtio"
    "-net" "user"
    "-usb"
    "-device" "usb-tablet"
)

if [ "$SERIAL_DEBUG" = true ]; then
    echo -e "${GREEN}Serial:${RESET}    Attached to stdio"
    QEMU_ARGS+=("-serial" "stdio")
fi

# KVM Acceleration check
if [ "$ENABLE_KVM" = true ]; then
    if [ -w /dev/kvm ] && [ -r /dev/kvm ]; then
        echo -e "${GREEN}KVM:${RESET}       ${BOLD}Enabled (hardware accelerated)${RESET}"
        QEMU_ARGS+=("-enable-kvm" "-cpu" "host")
    elif [ -e /dev/kvm ]; then
        echo -e "${YELLOW}KVM:${RESET}       /dev/kvm exists (run with sudo to enable full KVM speed)"
        QEMU_ARGS+=("-cpu" "max")
    else
        echo -e "${YELLOW}KVM:${RESET}       Disabled (/dev/kvm not found)"
        QEMU_ARGS+=("-cpu" "max")
    fi
else
    echo -e "${YELLOW}KVM:${RESET}       Disabled (by user flag)"
    QEMU_ARGS+=("-cpu" "max")
fi

# UEFI Configuration
if [ "$BOOT_MODE" = "uefi" ]; then
    OVMF_CODE="/usr/share/edk2/OvmfX64/OVMF_CODE.fd"
    OVMF_VARS="/usr/share/edk2/OvmfX64/OVMF_VARS.fd"

    if [ -f "$OVMF_CODE" ] && [ -f "$OVMF_VARS" ]; then
        TMP_VARS=$(mktemp --suffix=_VARS.fd)
        cp "$OVMF_VARS" "$TMP_VARS"
        trap 'rm -f "$TMP_VARS"' EXIT

        QEMU_ARGS+=(
            "-drive" "if=pflash,format=raw,readonly=on,file=$OVMF_CODE"
            "-drive" "if=pflash,format=raw,file=$TMP_VARS"
        )
    else
        echo -e "${RED}Error: OVMF UEFI firmware files not found at $OVMF_CODE.${RESET}"
        echo "Falling back to BIOS..."
    fi
fi

echo -e "${BLUE}------------------------------------------------------------------------------${RESET}"
echo -e "${BOLD}Launching QEMU...${RESET}"
echo -e "${BLUE}------------------------------------------------------------------------------${RESET}"

# Execute QEMU
exec "$QEMU_BIN" "${QEMU_ARGS[@]}"
