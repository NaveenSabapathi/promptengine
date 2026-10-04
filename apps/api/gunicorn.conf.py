import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = 60
graceful_timeout = 45
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
worker_tmp_dir = "/tmp"
preload_app = False
# ProxyFix handles the single trusted proxy. Docker exposes no direct API port.
forwarded_allow_ips = ""
secure_scheme_headers = {}
accesslog = "-"
errorlog = "-"
# %(U)s excludes query strings: OAuth codes must never enter access logs.
access_log_format = "%(h)s %(m)s %(U)s %(s)s %(L)s"
capture_output = False

if not 1 <= workers <= 16 or not 1 <= threads <= 16:
    raise RuntimeError("Gunicorn worker/thread counts must be between 1 and 16")
