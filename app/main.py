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
# Defaults are aimed at the **internal Postgres** running in the cluster.
# In-cluster you'll override these with a Secret, locally you can export env vars.
DB_HOST = os.getenv("DB_HOST", "orders-postgres")  # k8s Service name by default
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "app_db")
DB_USER = os.getenv("DB_USER", "app_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "supersecretdev")


def get_db_connection():
    """Open a new DB connection with a small timeout so failures are fast."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=3,
    )
    return conn


def init_db():
    """
    Create the orders table if it doesn't exist.

    This runs once at startup. If Postgres isn't ready yet, we log the error
    instead of crashing the app. That way /healthz still works and the pod
    isn't killed by liveness probes.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                        id SERIAL PRIMARY KEY,
                        item TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    """
                )
        print("[INIT_DB] DB initialization successful", flush=True)
    except Exception as e:
        print(f"[INIT_DB] Failed to initialize DB: {e}", flush=True)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def track_request(endpoint):
    """Decorator to measure latency + status code for each endpoint."""
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


# Try to initialize the DB once at import time.
# If Postgres isn't reachable yet, we log and keep going so the app still starts.
try:
    init_db()
except Exception as e:
    print(f"[INIT_DB] Unexpected error during startup: {e}", flush=True)


@app.route("/healthz")
@track_request("/healthz")
def healthz():
    """Simple health check that does NOT depend on the database."""
    return jsonify({"status": "ok"}), 200


@app.route("/orders")
@track_request("/orders")
def orders():
    """Return orders from the Postgres DB (inside the cluster)."""
    conn = None
    try:
        conn = get_db_connection()
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
                cur.execute(
                    "SELECT id, item, status, created_at FROM orders ORDER BY id ASC;"
                )
                rows = cur.fetchall()
                result = [
                    {
                        "id": row["id"],
                        "item": row["item"],
                        "status": row["status"],
                        "created_at": row["created_at"].isoformat(),
                    }
                    for row in rows
                ]
                return jsonify(result), 200
    except Exception as e:
        # IMPORTANT: don't let DB errors crash the worker – log and return 500
        print(f"[ORDERS] Error talking to DB: {e}", flush=True)
        return jsonify({"error": "DB error"}), 500
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/metrics")
def metrics():
    data = generate_latest()
    return app.response_class(data, mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    # For local dev only; in Docker we use gunicorn
    app.run(host="0.0.0.0", port=port)