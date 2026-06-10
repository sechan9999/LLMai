"""
Backwards-compatible shim: python run_server.py

The real entry point lives in server/run.py so it gets packaged
into the PyPI wheel.
"""
from server.run import main

if __name__ == "__main__":
    main()
