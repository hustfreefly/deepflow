# DeepFlow Frontend E2E Test
# Dry-run mode: validates API contracts without spawning agents
# Usage: python3 tests/test_frontend_e2e.py

import subprocess
import sys
import time
import json
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:17789"
TIMEOUT = 10

class E2ETest:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def check(self, name: str, condition: bool, detail: str = ""):
        status = "PASS" if condition else "FAIL"
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        self.results.append({"name": name, "status": status, "detail": detail})
        print(f"  [{status}] {name}")
        if detail and not condition:
            print(f"       → {detail}")
    
    def run(self):
        print("=" * 60)
        print("  DeepFlow Frontend E2E Test (Dry-Run)")
        print("=" * 60)
        
        # 1. Health Check
        print("\n📡 1. Health Check")
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
            self.check("Health endpoint", r.status_code == 200)
            if r.status_code == 200:
                data = r.json()
                self.check("Health fields", 
                          all(k in data for k in ["status", "version", "openclaw"]),
                          f"Response: {data}")
        except Exception as e:
            self.check("Health endpoint", False, str(e))
        
        # 2. System Info
        print("\n⚙️  2. System Info")
        try:
            r = requests.get(f"{BASE_URL}/api/v2/system-info", timeout=TIMEOUT)
            self.check("System info endpoint", r.status_code == 200)
            if r.status_code == 200:
                data = r.json()
                self.check("System info fields",
                          all(k in data for k in ["openclaw", "backend", "blackboard"]),
                          f"Missing fields in {list(data.keys())}")
        except Exception as e:
            self.check("System info endpoint", False, str(e))
        
        # 3. Sessions List
        print("\n📋 3. Sessions List")
        try:
            r = requests.get(f"{BASE_URL}/api/v2/sessions?limit=10", timeout=TIMEOUT)
            self.check("Sessions endpoint", r.status_code == 200)
            if r.status_code == 200:
                data = r.json()
                self.check("Sessions is array", isinstance(data, list))
                if len(data) > 0:
                    self.check("Session fields",
                              all(k in data[0] for k in ["session_id", "domain", "status", "created_at"]),
                              f"First session keys: {list(data[0].keys())}")
        except Exception as e:
            self.check("Sessions endpoint", False, str(e))
        
        # 4. Active Task
        print("\n🔍 4. Active Task")
        try:
            r = requests.get(f"{BASE_URL}/api/v2/active-task", timeout=TIMEOUT)
            self.check("Active task endpoint", r.status_code in [200, 204])
        except Exception as e:
            self.check("Active task endpoint", False, str(e))
        
        # 5. Task Submission (dry-run)
        print("\n📝 5. Task Submission (dry-run)")
        try:
            r = requests.post(
                f"{BASE_URL}/api/v2/tasks",
                json={"domain": "solution", "topic": "E2E Test", "session_prefix": "e2e_"},
                timeout=TIMEOUT
            )
            self.check("Task creation", r.status_code == 200)
            if r.status_code == 200:
                data = r.json()
                self.check("Task response fields",
                          all(k in data for k in ["session_id", "status"]),
                          f"Response keys: {list(data.keys())}")
                # Cleanup: mark as completed so it doesn't stay pending
                session_id = data.get("session_id")
                if session_id:
                    requests.post(
                        f"{BASE_URL}/api/v2/status/{session_id}",
                        json={"status": "completed"},
                        timeout=TIMEOUT
                    )
        except Exception as e:
            self.check("Task creation", False, str(e))
        
        # Summary
        print("\n" + "=" * 60)
        print(f"  Results: {self.passed} passed, {self.failed} failed, {self.passed + self.failed} total")
        status = "✅ ALL PASS" if self.failed == 0 else f"⚠️  {self.failed} FAILED"
        print(f"  Status: {status}")
        print("=" * 60)
        
        return self.failed == 0

if __name__ == "__main__":
    import requests
    test = E2ETest()
    success = test.run()
    sys.exit(0 if success else 1)
