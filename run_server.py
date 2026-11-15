import uvicorn

from itdesk_core.config import load_config
from server.main import app


def main():
    s = load_config()["server"]
    uvicorn.run(app, host=s["host"], port=int(s["port"]))


if __name__ == "__main__":
    main()
