# Launch Checklist

Use this checklist before handing the local build to an operator.

- Run `pytest tests/test_e2e.py -q`.
- Run `pytest -q`.
- Run `npm run build`.
- Run `npm test`.
- Confirm `.env.example` contains only local defaults and no secrets.
- Confirm `.gitignore` blocks `.env*`, secret files, local API data, and local model caches.
- Confirm `./scripts/launch-local.sh` starts on `127.0.0.1:4321` or another approved loopback port.
- Confirm `/health` returns `{"status":"ok"}` when the local API is running.
- Confirm `ffmpeg` and `ffprobe` are installed on the target machine.
- Confirm the operator understands model and GPU setup are local environment actions.
