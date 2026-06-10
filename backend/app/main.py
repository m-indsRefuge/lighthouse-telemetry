from app.collectors.cpu import get_cpu_info
from app.collectors.disk import get_disk_info
from app.collectors.memory import get_memory_info
from app.collectors.processes import get_top_processes
from app.collectors.system import get_system_info
from app.reporting.console_report import print_console_report


def collect_telemetry() -> dict:
    return {
        "system": get_system_info(),
        "cpu": get_cpu_info(),
        "memory": get_memory_info(),
        "disk": get_disk_info(),
        "processes": get_top_processes(),
    }


def main() -> None:
    telemetry = collect_telemetry()
    print_console_report(telemetry)


if __name__ == "__main__":
    main()