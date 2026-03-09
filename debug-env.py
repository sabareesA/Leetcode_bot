import os
import sys

print("=" * 60)
print("DEBUG: Environment Loading Test")
print("=" * 60)

# Check current directory
print(f"\n📁 Current Directory: {os.getcwd()}")

# List all files
print(f"\n📄 Files in current directory:")
for f in os.listdir('.'):
    print(f"   - {f}")

# Check if .env exists
env_exists = os.path.exists('.env')
print(f"\n📋 .env file exists: {env_exists}")

if env_exists:
    print("\n📖 Content of .env file:")
    print("-" * 40)
    with open('.env', 'r') as f:
        content = f.read()
        print(content)
    print("-" * 40)

    # Check for common issues
    if '\ufeff' in content:
        print("⚠️ WARNING: File has BOM character (encoding issue)")
    if '=' not in content:
        print("⚠️ WARNING: No '=' found in file")

# Try loading with dotenv
print("\n🔄 Attempting to load with python-dotenv...")
try:
    from dotenv import load_dotenv
    result = load_dotenv()
    print(f"   load_dotenv() returned: {result}")
except ImportError:
    print("❌ python-dotenv not installed!")
    print("   Run: pip install python-dotenv")
    sys.exit(1)

# Check environment variables
print("\n🔑 Environment Variables:")
token = os.getenv('TELEGRAM_BOT_TOKEN')
group_id = os.getenv('GROUP_CHAT_ID')

if token:
    print(f"   ✅ TELEGRAM_BOT_TOKEN = {token[:15]}...{token[-5:]}")
else:
    print("   ❌ TELEGRAM_BOT_TOKEN = None (NOT LOADED!)")

if group_id:
    print(f"   ✅ GROUP_CHAT_ID = {group_id}")
else:
    print("   ❌ GROUP_CHAT_ID = None (NOT LOADED!)")

print("\n" + "=" * 60)
