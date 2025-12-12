#!/usr/bin/env python3
"""
Create Lambda deployment ZIP for deepseek-call
"""
import os
import zipfile
from pathlib import Path

def create_lambda_zip():
    lambda_dir = Path(__file__).parent
    package_dir = lambda_dir / 'package'
    zip_path = lambda_dir / 'deepseek-call.zip'
    
    # Remove old zip if exists
    if zip_path.exists():
        zip_path.unlink()
        print(f"Removed old {zip_path}")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add all files from package directory (dependencies)
        if package_dir.exists():
            print(f"Adding dependencies from {package_dir}...")
            for root, dirs, files in os.walk(package_dir):
                for file in files:
                    file_path = Path(root) / file
                    # Calculate relative path from package directory
                    arcname = file_path.relative_to(package_dir)
                    zipf.write(file_path, arcname)
                    if len(files) < 10:  # Only print if not too many files
                        print(f"  Added: {arcname}")
        
        # Add lambda_function.py at root level
        lambda_function = lambda_dir / 'lambda_function.py'
        if lambda_function.exists():
            zipf.write(lambda_function, 'lambda_function.py')
            print(f"Added: lambda_function.py")
        else:
            print(f"WARNING: {lambda_function} not found!")
    
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"\n✓ Created {zip_path} ({size_mb:.2f} MB)")
    return zip_path

if __name__ == '__main__':
    create_lambda_zip()
