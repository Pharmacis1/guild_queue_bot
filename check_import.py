import sys
import os

try:
    from routers import api
    print("Import Successful")
except Exception as e:
    print(f"Import Failed: {e}")
except SyntaxError as e:
    print(f"Syntax Error: {e}")
