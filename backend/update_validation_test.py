"""
Auto-update stress_test_with_validation.py
- Change model to Claude Sonnet
- Extend test up to 3000 concurrent users
"""

import re

def update_validation_test():
    """Update the validation test configuration"""
    
    file_path = "stress_test_with_validation.py"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print("="*60)
        print("🔧 UPDATING VALIDATION TEST")
        print("="*60)
        print()
        
        changes_made = []
        
        # Change 1: Update model from gemini to claude
        old_model = '"model": "gemini-1.5-flash"'
        new_model = '"model": "claude-sonnet-4"'
        
        if old_model in content:
            content = content.replace(old_model, new_model)
            changes_made.append("✅ Changed model: gemini-1.5-flash → claude-sonnet-4")
        else:
            print("⚠️  Warning: gemini-1.5-flash not found, checking alternatives...")
            # Try alternative patterns
            content = re.sub(
                r'"model":\s*"gemini-[^"]*"',
                '"model": "claude-sonnet-4"',
                content
            )
            changes_made.append("✅ Updated model to claude-sonnet-4")
        
        # Change 2: Update test levels to go up to 3000
        old_levels = 'LEVELS = [100, 250, 500, 1000, 1500]'
        new_levels = 'LEVELS = [100, 250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500, 2750, 3000]'
        
        if old_levels in content:
            content = content.replace(old_levels, new_levels)
            changes_made.append("✅ Extended levels: 100 → 3000 users (13 levels)")
        else:
            print("⚠️  Warning: exact LEVELS pattern not found, trying regex...")
            # Try to find and replace LEVELS array
            pattern = r'LEVELS\s*=\s*\[[^\]]+\]'
            replacement = 'LEVELS = [100, 250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500, 2750, 3000]'
            
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                changes_made.append("✅ Extended levels: 100 → 3000 users (13 levels)")
            else:
                changes_made.append("⚠️  Could not find LEVELS array")
        
        # Change 3: Update the description text
        content = content.replace(
            'Explain AI concept #',
            'Explain advanced concept #'
        )
        changes_made.append("✅ Updated prompt text")
        
        # Change 4: Update any display text mentioning gemini
        content = content.replace('gemini', 'claude')
        content = content.replace('Gemini', 'Claude')
        changes_made.append("✅ Updated display text")
        
        # Write the modified content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("Changes applied:")
        for change in changes_made:
            print(f"  {change}")
        
        print()
        print("="*60)
        print("✅ VALIDATION TEST UPDATED!")
        print("="*60)
        print()
        print("New configuration:")
        print("  • Model: claude-sonnet-4")
        print("  • Test levels: 100 → 3000 users (13 levels)")
        print("  • Increment: ~250 users per level")
        print()
        print("Expected test duration: ~4-5 minutes")
        print("  (13 levels × ~20 seconds each)")
        print()
        print("Ready to run:")
        print("  python stress_test_with_validation.py")
        print()
        print("="*60)
        
        return True
        
    except FileNotFoundError:
        print(f"❌ Error: {file_path} not found!")
        print()
        print("Make sure you're in the correct directory.")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    update_validation_test()
