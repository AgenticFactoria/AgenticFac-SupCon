"""
Safe output utilities to handle BrokenPipeError when using pipes
"""

import sys


def safe_print(*args, **kwargs):
    """
    Safe print function that handles BrokenPipeError when output is piped
    """
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        # When piped to head/tail, ignore broken pipe errors
        sys.stderr.close()
    except KeyboardInterrupt:
        sys.exit(1)
