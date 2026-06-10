from lighthouse.collectors.system import collect_system_snapshot

def main():
    snapshot = collect_system_snapshot()
    print(snapshot)

if __name__ == "__main__":
    main()
