"""
E2E Test: Frontend complete flow.
Tests: submit task → consumer processes → status updates → report generated.
"""
import pytest
import time
import json
from pathlib import Path
import requests

# Test configuration
BASE_URL = "http://localhost:8000/api"
TASK_QUEUE_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "frontend" / "task_queue"
BLACKBOARD_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"


class TestFrontendFlow:
    """End-to-end test for frontend task flow."""
    
    def test_health_check(self):
        """Test API is running."""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_submit_solution_task(self):
        """Test submitting a solution task."""
        task_data = {
            "domain": "solution",
            "topic": "Test architecture design",
            "solution_type": "architecture",
            "constraints": ["Budget 1M"],
            "stakeholders": ["Dev Team"],
            "session_prefix": "e2e-test"
        }
        
        response = requests.post(f"{BASE_URL}/tasks", json=task_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "queued"
        assert data["domain"] == "solution"
        assert "session_id" in data
        
        # Save for later tests
        self.session_id = data["session_id"]
        print(f"Created task: {self.session_id}")
    
    def test_task_queued_in_filesystem(self):
        """Test task is saved to filesystem queue."""
        # Get session_id from previous test
        task_files = list(TASK_QUEUE_DIR.glob("e2e-test_*_request.json"))
        assert len(task_files) > 0, "Task file not found in queue"
        
        task_file = task_files[0]
        with open(task_file, 'r') as f:
            task = json.load(f)
        
        assert task["status"] == "queued"
        assert task["domain"] == "solution"
    
    def test_status_file_created(self):
        """Test status.json is initialized in blackboard."""
        task_files = list(TASK_QUEUE_DIR.glob("e2e-test_*_request.json"))
        task_file = task_files[0]
        
        with open(task_file, 'r') as f:
            task = json.load(f)
        
        session_id = task["session_id"]
        status_path = BLACKBOARD_DIR / session_id / "status.json"
        
        assert status_path.exists(), f"Status file not found: {status_path}"
        
        with open(status_path, 'r') as f:
            status = json.load(f)
        
        assert status["session_id"] == session_id
        assert status["status"] == "queued"
        assert len(status["stages"]) == 9  # 9 pipeline stages
    
    def test_consumer_status(self):
        """Test consumer is running."""
        response = requests.get(f"{BASE_URL}/consumer/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["running"] is True
        assert data["queue_dir"] is not None
    
    def test_task_execution_flow(self):
        """Test full task execution with status updates."""
        # Submit a test task
        task_data = {
            "domain": "solution",
            "topic": "Quick test task",
            "solution_type": "architecture",
            "session_prefix": "e2e-flow-test"
        }
        
        response = requests.post(f"{BASE_URL}/tasks", json=task_data)
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        
        # Poll for status changes (with timeout)
        max_wait = 60  # seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = requests.get(f"{BASE_URL}/status/{session_id}")
            if response.status_code == 200:
                status = response.json()
                print(f"Status: {status['status']}, Progress: {status['progress']}")
                
                if status["status"] in ["completed", "failed"]:
                    break
            
            time.sleep(2)
        
        # Verify task completed
        response = requests.get(f"{BASE_URL}/status/{session_id}")
        status = response.json()
        
        assert status["status"] == "completed"
        assert status["progress"] == 1.0
        assert "completed_at" in status
    
    def test_list_tasks(self):
        """Test listing tasks."""
        response = requests.get(f"{BASE_URL}/tasks")
        assert response.status_code == 200
        
        tasks = response.json()
        assert isinstance(tasks, list)
        assert len(tasks) > 0
    
    def test_get_task_details(self):
        """Test getting task details."""
        # Get latest task
        response = requests.get(f"{BASE_URL}/tasks?limit=1")
        tasks = response.json()
        
        if tasks:
            session_id = tasks[0]["session_id"]
            response = requests.get(f"{BASE_URL}/tasks/{session_id}")
            assert response.status_code == 200
            
            task = response.json()
            assert task["session_id"] == session_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
