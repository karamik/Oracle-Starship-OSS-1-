#!/bin/bash
# OSS-1 Analysis Script
# Compares baseline and defect recordings to identify damaged tiles

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
RECORDINGS_DIR="./recordings"
OUTPUT_REPORT="report.html"

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

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log ERROR "Docker not found. Please install Docker first."
        exit 1
    fi
    log INFO "Docker found"
}

# Run analysis using Docker container
run_analysis() {
    local baseline_session="$1"
    local defect_session="$2"
    
    log STEP "Starting OSS-1 Analysis"
    log INFO "Baseline: $baseline_session"
    log INFO "Defect: $defect_session"
    
    local baseline_dir="$RECORDINGS_DIR/$baseline_session"
    local defect_dir="$RECORDINGS_DIR/$defect_session"
    
    if [[ ! -d "$baseline_dir" ]]; then
        log ERROR "Baseline directory not found: $baseline_dir"
        exit 1
    fi
    
    if [[ ! -d "$defect_dir" ]]; then
        log ERROR "Defect directory not found: $defect_dir"
        exit 1
    fi
    
    # Run the Docker container with volumes mounted
    docker run --rm \
        -v "$(pwd)/recordings:/app/recordings" \
        -v "$(pwd)/models:/app/models" \
        -v "$(pwd)/config:/app/config" \
        -v "$(pwd)/src:/app/src" \
        ghcr.io/karamik/oss-1-pilot:latest \
        python /app/src/main_analyzer.py \
            --baseline "$baseline_session" \
            --defect "$defect_session" \
            --output "/app/$OUTPUT_REPORT"
    
    if [[ $? -eq 0 ]]; then
        log INFO "Analysis complete. Report generated: $OUTPUT_REPORT"
        
        # Try to open report in browser if on local machine
        if [[ -f "$OUTPUT_REPORT" ]]; then
            log INFO "Opening report in browser..."
            if command -v xdg-open &> /dev/null; then
                xdg-open "$OUTPUT_REPORT"
            elif command -v open &> /dev/null; then
                open "$OUTPUT_REPORT"
            elif command -v start &> /dev/null; then
                start "$OUTPUT_REPORT"
            else
                log INFO "Please open $OUTPUT_REPORT manually"
            fi
        fi
    else
        log ERROR "Analysis failed"
        exit 1
    fi
}

# Function to list available sessions
list_sessions() {
    log STEP "Available recording sessions:"
    if [[ -d "$RECORDINGS_DIR" ]]; then
        ls -1 "$RECORDINGS_DIR"
    else
        log WARN "No recordings found. Run ./record.sh first."
    fi
}

# Show usage
usage() {
    echo "Usage: ./analyze.sh <baseline_session> <defect_session>"
    echo "       ./analyze.sh --list"
    echo ""
    echo "Examples:"
    echo "  ./analyze.sh baseline defect"
    echo "  ./analyze.sh --list"
}

# Main
main() {
    if [[ "$1" == "--list" || "$1" == "-l" ]]; then
        list_sessions
        exit 0
    fi
    
    if [[ $# -ne 2 ]]; then
        usage
        exit 1
    fi
    
    check_docker
    run_analysis "$1" "$2"
}

main "$1" "$2"
