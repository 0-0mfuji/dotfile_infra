import asyncio
import json
import urllib.request
import urllib.error
from pathlib import Path
from nanomuse.config import load_settings
from nanomuse.tools.mcp_tools import MCPManager
cfg=load_settings('/home/secretary/.nanomuse/config.toml')
assert cfg.server.auth and cfg.server.host=='127.0.0.1'
assert not cfg.cloud.required and not cfg.cloud.sync and not cfg.hub.enabled
assert cfg.agent.language=='ja'
base='http://127.0.0.1:8787'
token=Path('/home/secretary/.nanomuse/server_token').read_text().strip()
def get(path, auth=True):
    req=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token} if auth else {})
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)
assert get('/api/health',False)['auth']
try: get('/api/files',False)
except urllib.error.HTTPError as e: assert e.code==401
else: raise AssertionError('unauthenticated access permitted')
files=get('/api/files')
assert any(f['path']=='NanoMuseの使い方.md' for f in files), files
print('HTTP/auth/Library/config: OK; documents:',len(files))
async def check_mcp():
    manager=MCPManager(cfg.mcp.servers)
    try:
        tools=await manager.connect()
        assert 'secretary__timetree_snapshot' in [t.name for t in tools]
        assert all(t.name.startswith('secretary__') for t in tools)
        tool=next(t for t in tools if t.name=='secretary__timetree_snapshot')
        result=await tool.execute()
        print('MCP initialize/list/call: OK; readonly tools:',len(tools))
    finally: await manager.close()
asyncio.run(check_mcp())
