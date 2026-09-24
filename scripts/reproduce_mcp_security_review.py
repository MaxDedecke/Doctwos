"""Run bounded MCP security regressions using rollback-only TEMP tables.

Requires the repository's .venv, .env and local PostgreSQL with migrated schema.
All data is synthetic. No embedding provider or running API service is called.
"""
import asyncio
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from cryptography.fernet import Fernet
os.environ['MASTER_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
import httpx
import mcp_server as server
from models.database import (User, Team, TeamMembership, Project, ProjectMembership,
    KnowledgeSource, DocumentChunk, MCPAccessToken, CodeEntity, CodeEdge)
from api.mcp_tokens import revoke_token
from fastapi import HTTPException
from services import ollama_client

results = []
def record(name, condition, detail=None):
    assert condition, f'Unexpected result: {name}: {detail}'
    results.append({'check': name, 'status': 'PASS', 'detail': detail})

async def run(db):
    now = datetime.now(timezone.utc)
    user = User(id=-8101, username='audit-reader', role='user', is_active=True)
    disabled = User(id=-8102, username='audit-disabled', role='user', is_active=False)
    db.add_all([user, disabled, Team(id=-8201, name='audit-team'), Team(id=-8202, name='foreign-team')])
    db.flush()
    db.add_all([
        TeamMembership(id=-8301, user_id=user.id, team_id=-8201),
        Project(id=-8401, name='allowed', team_id=-8201),
        Project(id=-8402, name='foreign', team_id=-8202),
        ProjectMembership(id=-8501, user_id=user.id, project_id=-8401),
        KnowledgeSource(id=-8601, name='allowed-source', type='Git', project_id=-8401, team_id=-8201),
        KnowledgeSource(id=-8602, name='foreign-source', type='Git', project_id=-8402, team_id=-8202),
        DocumentChunk(id=-8701, project_id=-8401, source_id=-8601, file_path='allowed.txt',
            content='SYNTHETIC_ALLOWED', embedding=[0, 1, 0], embedding_dimension=3, embedding_model='audit-model'),
        DocumentChunk(id=-8702, project_id=-8402, source_id=None, file_path='foreign.txt',
            content='SYNTHETIC_FOREIGN_SOURCELESS', embedding=[1, 0, 0], embedding_dimension=3, embedding_model='audit-model'),
        DocumentChunk(id=-8703, project_id=-8402, source_id=-8602, file_path='foreign-sourced.txt',
            content='SYNTHETIC_FOREIGN_SOURCE', embedding=[1, 0.1, 0], embedding_dimension=3, embedding_model='audit-model'),
        CodeEntity(id=-8801, project_id=-8401, source_id=-8601, name='AllowedRoot', type='program', file_path='allowed.cbl'),
        CodeEntity(id=-8802, project_id=-8402, source_id=-8602, name='ForeignRoot', type='program', file_path='foreign.cbl'),
    ])
    secrets = {}
    for i, name in enumerate(['valid', 'revoked', 'expired', 'disabled', 'foreign-owner']):
        secret = 'dct_mcp_synthetic_audit_only_' + name
        secrets[name] = secret
        db.add(MCPAccessToken(id=-8900-i, user_id=disabled.id if name in ('disabled', 'foreign-owner') else user.id,
            name='synthetic-'+name, token_hash=hashlib.sha256(secret.encode()).hexdigest(), token_prefix=secret[:16],
            expires_at=now+timedelta(days=-1 if name=='expired' else 1),
            revoked_at=now if name=='revoked' else None))
    for i in range(180):
        db.add(CodeEdge(id=-9000-i, project_id=-8401, source_id=-8601, src_entity_id=-8801,
            dst_entity_id=-8801, dst_name='AllowedRoot', type='CALL', resolution='resolved', src_start_line=i+1))
    db.commit()  # releases only a savepoint; outer TEMP-table transaction is always rolled back

    profile=SimpleNamespace(model='audit-model', provider='ollama', base_url='http://unused.invalid', path='/api/embed',
        api_key=None, dimension=3, context_length=100)
    with ExitStack() as stack:
        stack.enter_context(patch.object(server, 'SessionLocal', lambda: db))
        stack.enter_context(patch.object(db, 'close', lambda: None))
        stack.enter_context(patch.object(server, 'record_mcp_tool_call', lambda *a, **kw: None))
        stack.enter_context(patch.object(server, 'get_active_embedding_profile', lambda _: profile))
        embedding = stack.enter_context(patch.object(ollama_client, 'embed_text', AsyncMock(return_value=[1, 0, 0])))
        async with server.mcp.session_manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.asgi_app), base_url='http://localhost:8000') as client:
                base = {'Accept':'application/json, text/event-stream', 'Authorization':'Bearer '+secrets['valid']}
                init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26',
                    'capabilities':{},'clientInfo':{'name':'synthetic-security-review','version':'1'}}}
                async def post(body, headers=None):
                    return await client.post('/mcp', json=body, headers=base if headers is None else headers)
                async def call(name, args):
                    response=await post({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':args}})
                    assert response.status_code==200, response.status_code
                    return response.json()['result']
                def data(result):
                    return result.get('structuredContent') or json.loads(result['content'][0]['text'])
                response=await post(init)
                record('valid bearer initializes', response.status_code==200, response.status_code)
                for name in ('missing','invalid','revoked','expired','disabled'):
                    headers={'Accept':base['Accept']}
                    if name!='missing': headers['Authorization']='Bearer '+secrets.get(name, 'dct_mcp_no_such_token')
                    response=await post(init, headers)
                    record(name+' credential denied', response.status_code==401, response.status_code)
                response=await post(init, [('Accept',base['Accept']),('Authorization',base['Authorization']),('Authorization',base['Authorization'])])
                record('duplicate authorization denied',response.status_code==401,response.status_code)
                for name, headers, expected in [('untrusted host',{**base,'Host':'attacker.invalid'},421),
                    ('untrusted origin',{**base,'Origin':'https://attacker.invalid'},403)]:
                    response=await post(init,headers)
                    record(name+' denied',response.status_code==expected,response.status_code)
                response=await client.post('/mcp', content=b'{' + b' ' * 262145, headers={**base,'Content-Type':'application/json'})
                record('oversized body denied',response.status_code==413,response.status_code)
                response=await client.post('/mcp', content=b'{bad', headers={**base,'Content-Type':'application/json'})
                record('malformed JSON denied',response.status_code==400,response.status_code)
                response=await post({'jsonrpc':'2.0','id':3,'method':'tools/list'})
                tools=response.json()['result']['tools']
                record('six read-only tools',len(tools)==6 and all(t['annotations']['readOnlyHint'] for t in tools),[t['name'] for t in tools])
                visible=data(await call('list_visible_projects',{}))
                record('project list scope', [p['id'] for p in visible['projects']]==[-8401])
                for name,args in [('search_code',{'project_id':-8402,'query':'Foreign'}),
                    ('get_code_entity',{'project_id':-8401,'entity_id':-8802}),
                    ('get_call_flow',{'project_id':-8401,'entity_id':-8802}),
                    ('get_graph_neighbors',{'project_id':-8401,'entity_id':-8802}),
                    ('search_knowledge',{'project_id':-8402,'query':'foreign'})]:
                    value=await call(name,args)
                    record(name+' direct foreign access denied',value.get('isError') is True)
                record('denied knowledge query never embeds',embedding.await_count==0)
                value=data(await call('search_code',{'project_id':-8401,'query':"' OR 1=1 --"}))
                record('SQL injection string yields no matches',value['results']==[])
                value=await call('search_code',{'project_id':-8401,'query':'x'*201})
                record('query length enforced',value.get('isError') is True)
                value=data(await call('get_code_entity',{'project_id':-8401,'entity_id':-8801}))
                record('own entity readable',value['id']==-8801)
                value=data(await call('search_knowledge',{'project_id':-8401,'query':'synthetic','limit':8}))
                returned={r['chunk_id']:r for r in value['results']}
                record('foreign source-backed chunk suppressed',-8703 not in returned)
                record('foreign sourceless chunk blocked by MCP',-8702 not in returned,
                    {'foreign_chunk_returned':-8702 in returned})
                statements=[]
                def capture(conn,cursor,statement,parameters,context,executemany):
                    if 'FROM code_edges' in statement: statements.append(statement)
                event.listen(db.get_bind(),'before_cursor_execute',capture)
                try: value=data(await call('get_call_flow',{'project_id':-8401,'entity_id':-8801,'hops':1}))
                finally: event.remove(db.get_bind(),'before_cursor_execute',capture)
                record('call-flow SQL fetch has a database limit',bool(statements) and all('LIMIT' in s.upper() for s in statements),
                    {'synthetic_edges':180,'returned_edges':len(value['edges']),'sql_has_limit':all('LIMIT' in s.upper() for s in statements)})
                try: revoke_token(-8904,db=db,user=user)
                except HTTPException as exc: record('cannot revoke another users token',exc.status_code==404)
                else: raise AssertionError('foreign token revocation permitted')
                token=db.get(MCPAccessToken,-8900)
                token.revoked_at=now
                db.commit()
                response=await post(init)
                record('revocation enforced on next request',response.status_code==401,response.status_code)

url=make_url(os.environ.get('DATABASE_URL','postgresql://admin:change-me@db:5432/doctus')).set(host='127.0.0.1')
engine=create_engine(url,connect_args={'connect_timeout':3})
with engine.connect() as conn:
    outer=conn.begin()
    try:
        for model in [User,Team,TeamMembership,Project,ProjectMembership,KnowledgeSource,DocumentChunk,MCPAccessToken,CodeEntity,CodeEdge]:
            name=model.__tablename__
            conn.execute(text(f'CREATE TEMP TABLE "{name}" (LIKE public."{name}" INCLUDING DEFAULTS) ON COMMIT DROP'))
        db=Session(bind=conn,join_transaction_mode='create_savepoint')
        try: asyncio.run(run(db))
        finally: db.close()
    finally: outer.rollback()
print(json.dumps({'results':results,'cleanup':'outer transaction rolled back; TEMP tables removed'},indent=2))
