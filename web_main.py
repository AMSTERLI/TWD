import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "order_system.web.app:app",
        host=os.environ.get("TWD_HOST", "127.0.0.1"),
        port=int(os.environ.get("TWD_PORT", "8000")),
        workers=1,
        limit_concurrency=int(os.environ.get("TWD_MAX_CONNECTIONS", "40")),
        timeout_keep_alive=5,
        access_log=os.environ.get("TWD_ACCESS_LOG", "0") == "1",
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("TWD_FORWARDED_IPS", "127.0.0.1"),
    )
