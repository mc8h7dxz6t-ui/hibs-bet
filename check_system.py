#!/usr/bin/env python3
"""
HibsBetting System Check - Verify M5 setup and free API configuration.

Run this to verify everything is working before launching the apps:
    python check_system.py
"""

import os
import sys
import platform
from pathlib import Path

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_check(passed, item, details=""):
    status = "✅" if passed else "❌"
    print(f"{status} {item}")
    if details:
        print(f"   {details}")

def check_platform():
    """Check system platform compatibility"""
    print_header("1. SYSTEM & PLATFORM")
    
    system = platform.system()
    machine = platform.machine()
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    print(f"OS: {system}")
    print(f"Architecture: {machine}")
    print(f"Python Version: {python_version}")
    print(f"CPU Cores: {os.cpu_count()}")
    
    is_apple_silicon = machine == 'arm64'
    print_check(system == "Darwin", "macOS", "✅ Required for .app bundles")
    print_check(is_apple_silicon, "Apple Silicon (M-series)", "⚠️ Intel Macs also supported but not optimized")
    print_check(sys.version_info >= (3, 8), "Python 3.8+", f"Found: {python_version}")
    
    return is_apple_silicon

def check_venv():
    """Check virtual environment setup"""
    print_header("2. VIRTUAL ENVIRONMENT")
    
    venv_path = Path("/Users/philipmacleod/HibsBetting/.venv")
    print_check(venv_path.exists(), "Virtual environment exists", f"Path: {venv_path}")
    
    if venv_path.exists():
        activate_path = venv_path / "bin" / "activate"
        print_check(activate_path.exists(), "Activation script found", f"Path: {activate_path}")
        
        python_path = venv_path / "bin" / "python"
        print_check(python_path.exists(), "Python executable found", f"Path: {python_path}")

def check_env_file():
    """Check .env configuration file"""
    print_header("3. ENVIRONMENT CONFIGURATION (.env)")
    
    env_path = Path("/Users/philipmacleod/HibsBetting/.env")
    print_check(env_path.exists(), ".env file exists", f"Path: {env_path}")
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            content = f.read()
        
        required_keys = [
            'FOOTBALL_DATA_ORG_API_KEY',
            'API_SPORTS_API_KEY',
            'SPORTSMONK_API_KEY',
            'ODDS_API_KEY',
        ]
        
        for key in required_keys:
            has_key = key in content
            has_value = f"{key}=" in content and f"{key}=your_key" not in content
            print_check(has_key, f"Key: {key}")
            if has_key and not has_value:
                print("   ⚠️  WARNING: Key has placeholder value 'your_key'")

def check_app_bundles():
    """Check macOS .app bundles are properly set up"""
    print_header("4. macOS APP BUNDLES")
    
    apps = {
        "HibsBetting.app": "Flask Dashboard",
        "HibsBetting-Streamlit.app": "Streamlit Interface",
    }
    
    launch_dir = Path("/Users/philipmacleod/HibsBetting/launch")
    
    for app_name, description in apps.items():
        app_path = launch_dir / app_name
        print_check(app_path.exists(), f"{app_name} ({description})", f"Path: {app_path}")
        
        if app_path.exists():
            contents_dir = app_path / "Contents" / "MacOS"
            print_check(contents_dir.exists(), f"  Contents/MacOS/", str(contents_dir))
            
            info_plist = app_path / "Contents" / "Info.plist"
            print_check(info_plist.exists(), f"  Info.plist found", str(info_plist))

def check_requirements():
    """Check Python requirements are installed"""
    print_header("5. PYTHON REQUIREMENTS")
    
    requirements = [
        'flask',
        'pandas',
        'scikit-learn',
        'requests',
        'numpy',
        'streamlit',
        'python-dotenv',
        'joblib',
    ]
    
    missing = []
    for req in requirements:
        try:
            __import__(req)
            print_check(True, f"{req}")
        except ImportError:
            print_check(False, f"{req}", "❌ Not installed - run: pip install -r requirements.txt")
            missing.append(req)
    
    return len(missing) == 0

def check_m5_optimization():
    """Check M5 optimization module"""
    print_header("6. M5/APPLE SILICON OPTIMIZATION")
    
    sys.path.insert(0, "/Users/philipmacleod/HibsBetting/src")
    
    try:
        from hibs_predictor.m5_optimization import M5Optimizer
        
        is_apple_silicon = M5Optimizer.is_apple_silicon()
        print_check(True, "m5_optimization module loaded")
        
        if is_apple_silicon:
            settings = M5Optimizer.get_optimal_settings()
            print("  Optimal Settings for M-series:")
            for key, value in settings.items():
                print(f"    • {key}: {value}")
        else:
            print("  (Intel Mac detected - M-series optimizations not active)")
            
    except ImportError as e:
        print_check(False, "m5_optimization module", f"Error: {e}")

def check_rate_limiter():
    """Check rate limiter configuration"""
    print_header("7. FREE API RATE LIMITING")
    
    sys.path.insert(0, "/Users/philipmacleod/HibsBetting/src")
    
    try:
        from hibs_predictor.rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        print_check(True, "Rate limiter loaded")
        
        print("\nDaily API Limits (Free Tier):")
        for service, limit in limiter.limits.items():
            print(f"  • {service}: {limit} calls/day")
        
        # Try to print usage report
        try:
            print("\nCurrent Usage:")
            stats = limiter.get_all_stats()
            for service, stat in stats.items():
                used = stat['count']
                limit = stat['limit']
                pct = stat['usage_percent']
                print(f"  • {service}: {used}/{limit} ({pct:.0f}%)")
        except Exception as e:
            print(f"  (Could not retrieve current usage: {e})")
            
    except ImportError as e:
        print_check(False, "Rate limiter", f"Error: {e}")

def check_ports():
    """Check if required ports are available"""
    print_header("8. PORT AVAILABILITY")
    
    import socket
    
    ports = {
        5000: "Flask Dashboard",
        8501: "Streamlit Interface",
    }
    
    for port, service in ports.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        is_available = result != 0
        status = "Available" if is_available else "In use (stop the service first)"
        print_check(is_available, f"Port {port} ({service})", status)

def check_logs():
    """Check for recent log files"""
    print_header("9. LOG FILES")
    
    project_dir = Path("/Users/philipmacleod/HibsBetting")
    log_files = [
        "hibs_flask.log",
        "hibs_streamlit.log",
        ".rate_limit_state.json",
    ]
    
    for log_file in log_files:
        log_path = project_dir / log_file
        exists = log_path.exists()
        if exists:
            size = log_path.stat().st_size
            print_check(True, f"{log_file}", f"Size: {size} bytes")
        else:
            print_check(False, f"{log_file}", "(Will be created on first run)")

def print_summary(all_checks_passed):
    """Print final summary"""
    print_header("SYSTEM CHECK SUMMARY")
    
    if all_checks_passed:
        print("""
✅ ALL SYSTEMS GO!

Your HibsBetting installation is ready to run. You can now:

  1. Double-click HibsBetting.app or HibsBetting-Streamlit.app in Finder
  2. Or from terminal:
     source .venv/bin/activate
     python src/hibs_predictor/web.py

The apps are optimized for M-series Macs and free API tiers.
        """)
    else:
        print("""
⚠️  SOME ISSUES FOUND

Please address the ❌ items above before launching the apps.

Common fixes:
  • Missing requirements: pip install -r requirements.txt
  • Missing .env file: cp .env.example .env (then add API keys)
  • Virtual environment: python3 -m venv .venv && source .venv/bin/activate
  • API keys: https://www.football-data.org/register (and others)

See MACOS_QUICKSTART.md for detailed setup instructions.
        """)

def main():
    print("\n" + "="*60)
    print("  HibsBetting System Check")
    print("  M5 Optimization & Free API Setup Verification")
    print("="*60)
    
    try:
        # Run all checks
        check_platform()
        check_venv()
        check_env_file()
        check_app_bundles()
        all_requirements_installed = check_requirements()
        check_m5_optimization()
        check_rate_limiter()
        check_ports()
        check_logs()
        
        # Summary
        all_checks_passed = all_requirements_installed
        print_summary(all_checks_passed)
        
    except Exception as e:
        print(f"\n❌ ERROR during system check: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
