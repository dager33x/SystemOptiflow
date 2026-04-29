import os

import uvicorn

from webapp.main import app


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("web_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
