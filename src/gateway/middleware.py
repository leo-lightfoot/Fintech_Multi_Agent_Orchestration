"""Rate limiting middleware using slowapi.

Limits:
  - Task submission  : 20 requests/minute per IP  (each task can be expensive)
  - Read endpoints   : 100 requests/minute per IP
  - Auth endpoints   : 10 requests/minute per IP  (brute-force protection)

The limiter instance is imported by api.py and applied per-route with
the @limiter.limit() decorator.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Key function: rate-limit by client IP address.
# Swap get_remote_address for a user-id extractor once auth is enforced.
limiter = Limiter(key_func=get_remote_address)

# Re-export the handler so api.py only needs one import from this module
rate_limit_exceeded_handler = _rate_limit_exceeded_handler
RateLimitExceededError = RateLimitExceeded
