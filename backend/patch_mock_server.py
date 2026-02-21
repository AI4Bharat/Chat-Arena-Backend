"""
Auto-patch mock_server_realistic.py to add [DONE] marker
"""

import re
import os

def patch_mock_server():
    """Add [DONE] marker to mock server"""
    
    file_path = "mock_server_realistic.py"
    
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} not found!")
        return False
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already patched
    if 'data: [DONE]' in content:
        print("✅ File already patched! [DONE] marker exists.")
        return True
    
    # Pattern to find: the streaming loop followed by return or end of function
    # We'll add the [DONE] marker after the loop
    
    # Look for the pattern where we stream chunks
    pattern = r'(yield f"data: \{json\.dumps\(chunk_data\)\}\\n\\n"\s+await asyncio\.sleep\(WORD_DELAY\))'
    
    # Check if pattern exists
    if not re.search(pattern, content):
        print("⚠️  Warning: Expected pattern not found. Manual edit may be needed.")
        print("Looking for alternative pattern...")
        
        # Try alternative pattern
        pattern = r'(await asyncio\.sleep\(WORD_DELAY\)\s*\n\s*$)'
        
    # Add [DONE] marker after the loop
    # First, let's find where to insert
    lines = content.split('\n')
    
    modified = False
    new_lines = []
    in_streaming_function = False
    loop_indent = 0
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # Detect streaming function
        if 'async def streaming_response' in line or 'def streaming_response' in line:
            in_streaming_function = True
        
        # Find the streaming loop
        if in_streaming_function and 'for i, word in enumerate(words):' in line:
            loop_indent = len(line) - len(line.lstrip())
        
        # Find the end of the loop (await asyncio.sleep)
        if in_streaming_function and loop_indent > 0 and 'await asyncio.sleep(WORD_DELAY)' in line:
            current_indent = len(line) - len(line.lstrip())
            
            # Check if this is the last line of the loop
            # Look ahead to see if next line is dedented
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.strip():  # Not empty
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    # If next line is dedented, we're at the end of loop
                    if next_indent <= loop_indent:
                        # Add [DONE] marker with base indent (outside loop, inside function)
                        base_indent = ' ' * loop_indent
                        new_lines.append('')
                        new_lines.append(f'{base_indent}# Send completion marker')
                        new_lines.append(f'{base_indent}yield "data: [DONE]\\n\\n"')
                        modified = True
                        in_streaming_function = False
                        loop_indent = 0
    
    if not modified:
        print("⚠️  Could not automatically patch. Trying manual insertion...")
        
        # Fallback: Insert before the last line if it's a return or at the end
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            
            # If we find the streaming loop end, add marker
            if 'await asyncio.sleep(WORD_DELAY)' in line:
                # Check if next non-empty line is not indented (end of loop)
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j]
                    if next_line.strip():
                        curr_indent = len(line) - len(line.lstrip())
                        next_indent = len(next_line) - len(next_line.lstrip())
                        
                        if next_indent < curr_indent:
                            # Found end of loop
                            base_indent = ' ' * next_indent
                            new_lines.append('')
                            new_lines.append(f'{base_indent}# Send completion marker')
                            new_lines.append(f'{base_indent}yield "data: [DONE]\\n\\n"')
                            modified = True
                            break
                if modified:
                    break
    
    if not modified:
        print("❌ Could not automatically patch. Please manually add:")
        print("")
        print("After the 'await asyncio.sleep(WORD_DELAY)' line, add:")
        print("    # Send completion marker")
        print('    yield "data: [DONE]\\n\\n"')
        return False
    
    # Write the modified content
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    print("✅ Successfully patched mock_server_realistic.py!")
    print("")
    print("Added [DONE] marker to streaming response.")
    print("Restart your mock server for changes to take effect.")
    
    return True

if __name__ == "__main__":
    print("="*60)
    print("🔧 PATCHING MOCK SERVER")
    print("="*60)
    print("")
    
    success = patch_mock_server()
    
    print("")
    print("="*60)
    
    if success:
        print("✅ PATCH COMPLETE!")
        print("")
        print("Next steps:")
        print("  1. Restart mock server: python mock_server_realistic.py")
        print("  2. Run validation test: python stress_test_with_validation.py")
        print("  3. You should now see 100% complete responses!")
    else:
        print("⚠️ MANUAL PATCH NEEDED")
        print("")
        print("Edit mock_server_realistic.py manually:")
        print("")
        print("Find the streaming loop (around line 60-70):")
        print("    for i, word in enumerate(words):")
        print("        chunk_data = {...}")
        print('        yield f"data: {json.dumps(chunk_data)}\\n\\n"')
        print("        await asyncio.sleep(WORD_DELAY)")
        print("")
        print("Add AFTER the loop (at same indent level as 'for'):")
        print("    # Send completion marker")
        print('    yield "data: [DONE]\\n\\n"')
    
    print("="*60)
