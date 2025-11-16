import time
import os
from flask import Flask, jsonify, request, g
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# === Metrics ===
# Golden signal: how many requests by method/path/statuses
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

# Golden signal: latency per path
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["path"],
)

# Golden signal: errors by status code
ERROR_COUNT = Counter(
    "http_requests_errors_total",
    "Total HTTP error responses",
    ["status"],
)

# Placeholder for DB metrics (we'll wire real DB calls later)
DB_QUERY_COUNT = Counter(
    "db_queries_total",
    "Total DB queries (placeholder for now)",
    ["operation"],
)


# === Helper to record timing around every request ===
@app.before_request
def start_timer():
    g.start_time = time.time()


@app.after_request
def record_metrics(response):
    # Path can be noisy (ids, etc). For now we use the raw path.
    path = request.path
    method = request.method
    status = response.status_code

    # Request count
    REQUEST_COUNT.labels(method=method, path=path, status=status).inc()

    # Latency
    if hasattr(g, "start_time"):
        elapsed = time.time() - g.start_time
        REQUEST_LATENCY.labels(path=path).observe(elapsed)

    # Error count (4xx/5xx)
    if 400 <= status < 600:
        ERROR_COUNT.labels(status=str(status)).inc()

    return response


# === Health endpoint ===
@app.route("/healthz", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# === Dummy business endpoint ===
@app.route("/orders", methods=["GET"])
def list_orders():
    """
    In a real service this would hit a DB.
    Here it's a stub, but we increment a placeholder DB metric.
    """
    DB_QUERY_COUNT.labels(operation="select").inc()

    fake_orders = [
        {"id": 1, "item": "book", "status": "shipped"},
        {"id": 2, "item": "laptop", "status": "processing"},
    ]
    return jsonify(fake_orders), 200


# === Prometheus metrics endpoint ===
@app.route("/metrics", methods=["GET"])
def metrics():
    """
    Expose Prometheus metrics.
    Prometheus will scrape this endpoint periodically.
    """
    data = generate_latest()
    return app.response_class(data, mimetype=CONTENT_TYPE_LATEST)


# Local dev entrypoint
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=True)