import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "nationwide_rehab_sale_watch_mcp.api:app",
        host=os.getenv("REHAB_WATCH_HOST", "127.0.0.1"),
        port=int(os.getenv("REHAB_WATCH_PORT", "8010")),
        reload=False,
    )
