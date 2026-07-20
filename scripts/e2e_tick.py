#!/usr/bin/env python3
"""E2E tick driver — 调用 BatchDriver.tick() 输出下一步动作。"""
import json
import sys
from domains.deliver_pro.batch_driver import BatchDriver

PROJECT = sys.argv[1] if len(sys.argv) > 1 else "skill-health-cli"

driver = BatchDriver(PROJECT)
actions = driver.tick()

output = {
    "project": PROJECT,
    "status": driver.get_status(),
    "actions": [],
}

for a in actions:
    entry = {
        "wp_id": a["wp_id"],
        "action": a["action"],
        "has_spawn": a.get("spawn_params") is not None,
    }
    if a.get("spawn_params"):
        params = a["spawn_params"]
        if isinstance(params, list):
            entry["spawn_count"] = len(params)
            entry["spawn_params"] = params
        else:
            entry["spawn_count"] = 1
            entry["spawn_params"] = [params]
    if a.get("error"):
        entry["error"] = a["error"]
    output["actions"].append(entry)

print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
