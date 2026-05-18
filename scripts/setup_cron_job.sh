#!/bin/bash
# DeepFlow Cron Job Setup Script
# Sets up periodic task checking for failed webhook notifications

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$HOME/.openclaw/workspace/.deepflow"
CRON_SCRIPT="$WORKSPACE_DIR/agents/cron_task_checker.py"

echo "=== DeepFlow Cron Job Setup ==="
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "⚠️  This script is designed for macOS (launchd)"
    echo "   For Linux, consider using cron instead"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found"
    exit 1
fi

echo "✅ Python3 found: $(python3 --version)"

# Create LaunchAgent plist
PLIST_NAME="ai.openclaw.deepflow.cron.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Get absolute path to workspace
WORKSPACE_ABS="$(cd "$WORKSPACE_DIR" && pwd)"

echo "Creating LaunchAgent: $PLIST_PATH"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.openclaw.deepflow.cron</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$CRON_SCRIPT</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$WORKSPACE_ABS</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$WORKSPACE_ABS</string>
    </dict>
    
    <key>StartInterval</key>
    <integer>30</integer>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>/tmp/openclaw/deepflow-cron.log</string>
    
    <key>StandardErrorPath</key>
    <string>/tmp/openclaw/deepflow-cron-error.log</string>
    
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF

echo "✅ LaunchAgent plist created"

# Create log directory
mkdir -p /tmp/openclaw

echo "✅ Log directory created: /tmp/openclaw"

# Load the LaunchAgent
echo "Loading LaunchAgent..."
launchctl load "$PLIST_PATH" 2>/dev/null || {
    echo "⚠️  LaunchAgent already loaded or failed to load"
    echo "   Attempting to unload and reload..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
}

echo "✅ LaunchAgent loaded"

# Verify
echo ""
echo "=== Verification ==="
if launchctl list | grep -q "ai.openclaw.deepflow.cron"; then
    echo "✅ Cron job is running"
    launchctl list | grep "ai.openclaw.deepflow.cron"
else
    echo "❌ Cron job not found in launchctl list"
    exit 1
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Cron job will run every 30 seconds"
echo "Logs: /tmp/openclaw/deepflow-cron.log"
echo "Errors: /tmp/openclaw/deepflow-cron-error.log"
echo ""
echo "Commands:"
echo "  Start:  launchctl start ai.openclaw.deepflow.cron"
echo "  Stop:   launchctl stop ai.openclaw.deepflow.cron"
echo "  Status: launchctl list | grep deepflow-cron"
echo "  Unload: launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
