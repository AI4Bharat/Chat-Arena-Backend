"""
Real-time Server Monitoring
Monitors system resources during stress test

Run in separate terminal: python monitor_server.py
"""

import psutil
import time
import os

def monitor_resources(interval=2):
    """Monitor system resources"""
    print("="*70)
    print("REAL-TIME SERVER MONITORING")
    print("="*70)
    print()
    print("Press Ctrl+C to stop")
    print()
    print(f"{'Time':<10} {'CPU %':<10} {'Memory %':<12} {'Memory GB':<12} {'Threads':<10}")
    print("-" * 70)
    
    try:
        while True:
            # Get metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_gb = memory.used / (1024**3)
            
            # Get process count (rough thread estimate)
            process = psutil.Process(os.getpid())
            threads = process.num_threads()
            
            # Print
            timestamp = time.strftime("%H:%M:%S")
            print(
                f"{timestamp:<10} "
                f"{cpu_percent:<10.1f} "
                f"{memory_percent:<12.1f} "
                f"{memory_gb:<12.2f} "
                f"{threads:<10}"
            )
            
            # Warnings
            if cpu_percent > 80:
                print("  ⚠️  HIGH CPU USAGE!")
            if memory_percent > 80:
                print("  ⚠️  HIGH MEMORY USAGE!")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print()
        print("="*70)
        print("Monitoring stopped")


if __name__ == "__main__":
    monitor_resources()
