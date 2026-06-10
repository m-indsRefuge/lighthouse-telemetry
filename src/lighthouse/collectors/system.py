import psutil
from datetime import datetime

def collect_system_snapshot():
    return {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory()._asdict(),
        "disk": psutil.disk_usage("C:\\")._asdict(),
    }
