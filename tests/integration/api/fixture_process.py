"""TEST ONLY: real HTTP/decode/B0/storage with a fictional native OCR boundary.

Not a production entrypoint and never native/model quality evidence.
"""
import json
from pathlib import Path
import socket
import sys
import threading

import uvicorn

sys.path.insert(0, str(Path(__file__).parents[2] / "unit/pipeline"))
from test_compute_pipeline import FixtureEngine

from vietdoc.contracts.compute import default_contracts_dir
from vietdoc.entrypoints.api.app import create_app
from vietdoc.entrypoints.api.settings import Settings
from vietdoc.ml.release_manifest import load_release
from vietdoc.pipeline.service import B0Pipeline


def main():
    root = Path(sys.argv[1])
    settings = Settings(service_token="test-only-token", models_dir=root / "models",
                        attempts_dir=root / "attempts", contracts_dir=default_contracts_dir())
    pipeline = B0Pipeline(load_release(settings.models_dir, "test-b0"), FixtureEngine())
    application = create_app(settings, pipeline)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(32)
        server = uvicorn.Server(uvicorn.Config(application, access_log=False, log_config=None))
        def stop_on_input():
            sys.stdin.readline()
            server.should_exit = True
        threading.Thread(target=stop_on_input, daemon=True).start()
        (root / "port.json").write_text(json.dumps(listener.getsockname()[1]))
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
