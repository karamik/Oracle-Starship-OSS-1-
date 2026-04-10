# OSS-1 Self-Service Pilot Kit
# Makefile for quick setup and execution

.PHONY: help install clean record analyze pilot

help:
	@echo "OSS-1 Pilot Kit Commands:"
	@echo "  make install      - Pull Docker container and setup environment"
	@echo "  make record       - Record baseline or defect tile sounds"
	@echo "  make analyze      - Run analysis on recorded data"
	@echo "  make pilot        - Run full pilot (record baseline + defect + analyze)"
	@echo "  make clean        - Remove temporary files and containers"

install:
	@echo "🐳 Pulling OSS-1 Docker image..."
	docker pull ghcr.io/karamik/oss-1-pilot:latest
	@echo "✅ Installation complete. Run 'make pilot' to start."

record:
	@echo "🎤 Recording tile sounds..."
	./record.sh

analyze:
	@echo "🔍 Running defect analysis..."
	./analyze.sh

pilot:
	@echo "🚀 Starting OSS-1 full pilot..."
	@echo "Step 1: Record baseline (healthy panel)"
	./record.sh baseline
	@echo "Step 2: Introduce defect (or use existing)"
	@echo "Step 3: Record defective panel"
	./record.sh defect
	@echo "Step 4: Compare and analyze"
	./analyze.sh baseline defect
	@echo "✅ Pilot complete. Open report.html"

clean:
	@echo "🧹 Cleaning up..."
	rm -rf ./recordings/*.wav
	rm -rf ./report.html
	docker system prune -f
	@echo "✅ Clean complete."
