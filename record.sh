#!/bin/bash
# OSS-1 Recording Script
# Records tapping sounds from tiles for baseline or defect detection

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
RECORDINGS_DIR="./recordings"
SAMPLE_RATE=44100
DURATION=2  # seconds per tile

# Create recordings directory if it doesn't exist
mkdir -p "$RECORDINGS_DIR"

# Function to log
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        INFO)
            echo -e "${GREEN}[$timestamp] [INFO]${NC} $message"
            ;;
        WARN)
            echo -e "${YELLOW}[$timestamp] [WARN]${NC} $message"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] [ERROR]${NC} $message"
            ;;
        STEP)
            echo -e "${BLUE}[$timestamp] [STEP]${NC} $message"
            ;;
        *)
            echo -e "$message"
            ;;
    esac
}

# Check if sox or ffmpeg is available for recording
check_recorder() {
    if command -v rec &> /dev/null; then
        RECORDER="sox"
    elif command -v ffmpeg &> /dev/null; then
        RECORDER="ffmpeg"
    elif command -v arecord &> /dev/null; then
        RECORDER="arecord"
    else
        log ERROR "No recording tool found. Please install sox, ffmpeg, or alsa-utils."
        exit 1
    fi
    log INFO "Using recorder: $RECORDER"
}

# Record a single tile
record_tile() {
    local tile_id="$1"
    local output_file="$2"
    
    log INFO "Recording tile $tile_id -> $output_file"
    echo -n "Tap tile $tile_id now (or press Enter to skip, 'q' to quit): "
    read -r input
    
    if [[ "$input" == "q" ]]; then
        log INFO "Recording cancelled by user"
        exit 0
    fi
    
    if [[ -z "$input" ]]; then
        log WARN "Skipping tile $tile_id"
        return 1
    fi
    
    # Record based on available recorder
    case $RECORDER in
        sox)
            rec "$output_file" rate $SAMPLE_RATE silence 1 0.1 1% trim 0 $DURATION 2>/dev/null
            ;;
        ffmpeg)
            ffmpeg -f alsa -i default -t $DURATION -ar $SAMPLE_RATE "$output_file" -y 2>/dev/null
            ;;
        arecord)
            arecord -f cd -t wav -d $DURATION -r $SAMPLE_RATE "$output_file" 2>/dev/null
            ;;
    esac
    
    if [[ -f "$output_file" && -s "$output_file" ]]; then
        log INFO "Saved: $output_file"
        return 0
    else
        log ERROR "Failed to record tile $tile_id"
        return 1
    fi
}

# Main recording loop
main() {
    local session_name="$1"
    
    if [[ -z "$session_name" ]]; then
        log ERROR "Usage: ./record.sh <session_name>"
        log ERROR "Example: ./record.sh baseline"
        log ERROR "         ./record.sh defect"
        exit 1
    fi
    
    log STEP "Starting OSS-1 Recording Session: $session_name"
    
    check_recorder
    
    local session_dir="$RECORDINGS_DIR/$session_name"
    mkdir -p "$session_dir"
    
    log INFO "You will now record sounds for each tile."
    log INFO "Use a hard object (screwdriver handle, metal rod) to tap each tile."
    log INFO "Hold the microphone close to the tile."
    log INFO ""
    log INFO "Controls:"
    log INFO "  - Tap the tile and press Enter"
    log INFO "  - Press Enter without tapping to skip"
    log INFO "  - Type 'q' and press Enter to quit"
    log INFO ""
    
    local tile_count=0
    while true; do
        tile_count=$((tile_count + 1))
        local output_file="$session_dir/tile_$(printf "%03d" $tile_count).wav"
        
        record_tile "$tile_count" "$output_file"
        
        echo -n "Continue to next tile? (Y/n/q): "
        read -r cont
        if [[ "$cont" == "n" || "$cont" == "N" ]]; then
            break
        elif [[ "$cont" == "q" || "$cont" == "Q" ]]; then
            log INFO "Recording stopped by user"
            break
        fi
    done
    
    log INFO "Recording complete. Files saved in $session_dir"
    log INFO "Total tiles recorded: $(ls -1 "$session_dir"/*.wav 2>/dev/null | wc -l)"
}

# Run main with first argument as session name
main "$1"
