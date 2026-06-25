# AG-003 Manual Remediation Report

## Status

Completed manually because the AntiGravity quota was reached before AG-003 could be executed by AntiGravity itself.

## Source reviews

This remediation follows the AG-001 and AG-002 AntiGravity review findings.

AG-002 verified:

- the Lighthouse test suite was healthy
- `fastapi`, `starlette`, and `uvicorn` were listed but unused
- `requirements.txt` had an encoding issue
- `pywin32` was unconditional
- PowerShell subprocess usage was confined to read-only diagnostic collectors
- memory architecture still needs dedicated documentation

## Product decision

Lighthouse will not expose a public REST API.

Future model/tool communication should use a controlled MCP-style architecture with explicit approval boundaries, not FastAPI, Starlette, or Uvicorn.

## Manual remediation performed

`requirements.txt` was updated to:

- use UTF-8 without BOM
- remove unused REST API dependencies:
  - `fastapi`
  - `starlette`
  - `uvicorn`
- keep `pywin32` Windows-only:
  - `pywin32; platform_system == "Windows"`

## Scope

Modified only:

- `requirements.txt`
- files under `AntiGravity/`

No application source code was modified.
No tests were modified.
No dependencies were added.
No MCP implementation was started.
No AntiGravity CLI or SDK integration was added.

## Validation to run

From the repository root:

```powershell
python -m pytest tests
```

Optional requirements sanity check:

```powershell
python -c "from pathlib import Path; data=Path('requirements.txt').read_bytes(); assert not data.startswith(b'\\xff\\xfe'); assert not data.startswith(b'\\xef\\xbb\\xbf'); text=data.decode('utf-8'); low=text.lower(); assert 'fastapi' not in low; assert 'starlette' not in low; assert 'uvicorn' not in low; assert 'pywin32; platform_system == \"Windows\"' in text; print('requirements.txt sanity checks passed')"
```

## Next action

Return to the primary V1 build path after this remediation branch is validated and merged.
