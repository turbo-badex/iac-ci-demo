import os
import time

from flask import Flask, jsonify, request
import psycopg2
import psycopg2.extras

from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = Flask(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
)

# DB configuration from environment (set in Kubernetes)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "orders")
DB_USER = os.getenv("DB_USER", "orders_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "supersecretdev")


def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    return conn


def init_db():


    """Create the orders table if it doesn't exist."""
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                        id SERIAL PRIMARY KEY,
                        item TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    """
                )
    finally:
        conn.close()


# @app.before_first_request
# def startup():
    # Ensure DB schema exists
#    init_db()



def track_request(endpoint):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            start = time.time()
            status_code = 500  # default if something blows up before we set it
            try:
                response = fn(*args, **kwargs)
                # Response might be (body, status) or a Response object
                if isinstance(response, tuple):
                    status_code = response[1]
                else:
                    status_code = getattr(response, "status_code", 200)
                return response
            finally:
                duration = time.time() - start
                REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
                REQUEST_COUNT.labels(
                    method=request.method,
                    endpoint=endpoint,
                    http_status=str(status_code),
                ).inc()

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator

try:
    init_db()
except Exception as e:
    # In dev, we can log/print instead of crashing hard
    print(f"Warning: could not initialize DB on startup: {e}")

@app.route("/healthz")
@track_request("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/orders")
@track_request("/orders")
def orders():
    """Return orders from the Postgres DB."""
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Seed one order if table is empty
                cur.execute("SELECT COUNT(*) FROM orders;")
                count = cur.fetchone()[0]
                if count == 0:
                    cur.execute(
                        "INSERT INTO orders (item) VALUES (%s);",
                        ("first-order-from-db",),
                    )
                # Return all orders
                cur.execute("SELECT id, item, created_at FROM orders ORDER BY id ASC;")
                rows = cur.fetchall()
                result = [
                    {"id": row["id"], "item": row["item"], "created_at": row["created_at"].isoformat()}
                    for row in rows
                ]
                return jsonify(result), 200
    finally:
        conn.close()


@app.route("/metrics")
def metrics():
    data = generate_latest()
    return app.response_class(data, mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    # For local dev only; in Docker we use gunicorn
    app.run(host="0.0.0.0", port=port)