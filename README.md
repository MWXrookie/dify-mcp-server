# Dify FastMCP JWave Server

The deployment contains two containers:

- `dify-mcp`: FastMCP HTTP gateway on port `8001` and `/mcp`.
- `jwave-executor`: a separate image containing the packaged
  `jwave` Conda environment. It is reachable only on an internal Docker
  network and has no published host port.

The executor runs one request at a time and returns `stdout`, `stderr`,
`exit_code`, `timed_out`, and `duration_ms`.

## Dify configuration

- URL: `http://dify-mcp:8001/mcp`
- Dynamic Client Registration: off
- Custom header name: `Authorization`
- Custom header value: `Bearer <MCP_AUTH_TOKEN>`

The self-hosted Dify SSRF proxy must contain this private-domain allowlist:

```env
SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=dify-mcp
```

On the VM, retrieve the token with:

```bash
grep '^MCP_AUTH_TOKEN=' /home/wenxuan/dify-mcp-server/.env
```

## MCP tools

`jwave_environment` checks that the packaged environment is healthy.

`run_jwave_code` accepts a Python string and an optional timeout from 1 to 30
seconds. The code limit is 20,000 characters. The packaged environment includes
`jwave==0.2.1`, `jax==0.4.30`, `jaxlib==0.4.30`, `jaxdf==0.2.8`,
`equinox==0.11.10`, and `jaxtyping==0.3.11`.

Example code:

```python
import jax
import jwave
print(jax.devices())
print("jwave imported")
```

The executor image uses a non-root user, a read-only root filesystem, a
temporary filesystem, no Linux capabilities, CPU/memory/process limits, a
wall-clock timeout, and an internal-only network. It is still an arbitrary code
execution service, so only trusted Dify users should be allowed to call it.
