"""Local durable, content-addressed evolutionary memory and graph retrieval.

Tenant scope is an operator-selected namespace, not a remote authentication
boundary. HMAC authenticates individual retained records, not database freshness.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
from collections import deque

KINDS=('experiment','result','artifact','hypothesis','evidence')
RELATIONS=('produced','derived','supports','refutes','uses')
MAX_NODES=4096
MAX_EDGES=16384
MAX_BODY=131072
MAX_STORAGE=16*1024*1024


class IntegrityError(RuntimeError):
    """Retained graph content failed authentication."""


def canonical(value):
    try: return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
    except (ValueError,TypeError,OverflowError,RecursionError) as exc: raise ValueError('invalid JSON value') from exc


def _json_keys(value, depth=0):
    if depth>32: raise ValueError('JSON depth budget')
    if isinstance(value,dict):
        if any(type(k) is not str for k in value): raise ValueError('JSON keys must be strings')
        for v in value.values(): _json_keys(v,depth+1)
    elif isinstance(value,(list,tuple)):
        for v in value: _json_keys(v,depth+1)


def tokens(value):
    return set(re.findall(r'[^\W_]+',value.casefold(),flags=re.UNICODE))


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[a-f0-9]{64}',value): raise ValueError('invalid node id')
    return value


class GraphMemory:
    def __init__(self,path,key:bytes,tenant:str):
        if type(key) is not bytes or not 32<=len(key)<=4096 or type(tenant) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',tenant):
            raise ValueError('invalid graph namespace or key')
        self.path=Path(path);self._key=key;self.tenant=tenant
        with self._db(write=True,bootstrap=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS nodes (tenant TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,mac TEXT NOT NULL,PRIMARY KEY(tenant,id))')
            db.execute('CREATE TABLE IF NOT EXISTS edges (tenant TEXT NOT NULL,src TEXT NOT NULL,relation TEXT NOT NULL,dst TEXT NOT NULL,mac TEXT NOT NULL,PRIMARY KEY(tenant,src,relation,dst),FOREIGN KEY(tenant,src) REFERENCES nodes(tenant,id),FOREIGN KEY(tenant,dst) REFERENCES nodes(tenant,id))')
            db.execute('CREATE TABLE IF NOT EXISTS namespaces (tenant TEXT PRIMARY KEY, mac TEXT NOT NULL)')
            row=db.execute('SELECT mac FROM namespaces WHERE tenant=?',(self.tenant,)).fetchone()
            if row is None:
                if db.execute('SELECT 1 FROM nodes WHERE tenant=? LIMIT 1',(self.tenant,)).fetchone():
                    raise IntegrityError('namespace record missing')
                db.execute('INSERT INTO namespaces VALUES (?,?)',(self.tenant,self._sign('namespace')))
            else: self._check_namespace(db)


    @contextmanager
    def _db(self, *, write=False,bootstrap=False):
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            if not bootstrap: self._check_namespace(db)
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally: db.close()

    def _sign(self,*fields):
        return hmac.new(self._key,canonical(['omega-graph-v1',self.tenant,*fields]).encode(),hashlib.sha256).hexdigest()

    def _check_namespace(self,db):
        row=db.execute('SELECT mac FROM namespaces WHERE tenant=?',(self.tenant,)).fetchone()
        if not row or not isinstance(row[0],str) or not hmac.compare_digest(row[0],self._sign('namespace')):
            raise IntegrityError('namespace authentication failed')

    def _node_id(self,body):
        return hashlib.sha256(canonical([self.tenant,body]).encode()).hexdigest()

    def _decode(self,i,body,mac):
        if not isinstance(body,str) or len(body)>MAX_BODY or self._node_id(body)!=i or not isinstance(mac,str) or not hmac.compare_digest(mac,self._sign('node',i,body)):
            raise IntegrityError('node authentication failed')
        try:
            value=json.loads(body)
            if set(value)!={'kind','text','payload'} or value['kind'] not in KINDS or type(value['text']) is not str or not 1<=len(value['text'])<=4096 or type(value['payload']) is not dict or canonical(value)!=body:
                raise ValueError('invalid node')
        except (ValueError,TypeError,RecursionError) as exc: raise IntegrityError('invalid node body') from exc
        return value

    def _add(self,db,kind,text,payload):
        if kind not in KINDS or type(text) is not str or not 1<=len(text)<=4096 or type(payload) is not dict: raise ValueError('invalid graph node')
        _json_keys(payload)
        body=canonical({'kind':kind,'text':text,'payload':payload})
        if len(body)>MAX_BODY: raise ValueError('node body budget')
        i=self._node_id(body);mac=self._sign('node',i,body)
        existing=db.execute('SELECT body,mac FROM nodes WHERE tenant=? AND id=?',(self.tenant,i)).fetchone()
        if existing:
            self._decode(i,*existing);return i
        count,size=db.execute('SELECT count(*),coalesce(sum(length(body)),0) FROM nodes WHERE tenant=?',(self.tenant,)).fetchone()
        if count>=MAX_NODES or size+len(body)>MAX_STORAGE: raise ValueError('node capacity')
        db.execute('INSERT INTO nodes VALUES (?,?,?,?)',(self.tenant,i,body,mac))
        return i

    def add(self,kind,text,payload):
        with self._db(write=True) as db: return self._add(db,kind,text,payload)

    def _link(self,db,src,relation,dst):
        _id(src);_id(dst)
        if src==dst or relation not in RELATIONS: raise ValueError('invalid relation')
        for i in (src,dst):
            row=db.execute('SELECT body,mac FROM nodes WHERE tenant=? AND id=?',(self.tenant,i)).fetchone()
            if not row: raise ValueError('node missing in namespace')
            self._decode(i,*row)
        mac=self._sign('edge',src,relation,dst)
        old=db.execute('SELECT mac FROM edges WHERE tenant=? AND src=? AND relation=? AND dst=?',(self.tenant,src,relation,dst)).fetchone()
        if old:
            if not isinstance(old[0],str) or not hmac.compare_digest(old[0],mac): raise IntegrityError('edge authentication failed')
            return
        if db.execute('SELECT count(*) FROM edges WHERE tenant=?',(self.tenant,)).fetchone()[0]>=MAX_EDGES: raise ValueError('edge capacity')
        db.execute('INSERT INTO edges VALUES (?,?,?,?,?)',(self.tenant,src,relation,dst,mac))

    def link(self,src,relation,dst):
        with self._db(write=True) as db: self._link(db,src,relation,dst)

    def record_experiment(self,plan,result, *, title="experiment plan symbolic neural hybrid regression",result_text="experiment result validation and test RMSE"):
        with self._db(write=True) as db:
            a=self._add(db,'experiment',title,plan)
            b=self._add(db,'result',result_text,result)
            self._link(db,a,'produced',b)
            return a,b

    def snapshot(self):
        """Return the authenticated namespace snapshot and adjacency index."""
        with self._db() as db:
            count,size=db.execute('SELECT count(*),coalesce(sum(length(body)),0) FROM nodes WHERE tenant=?',(self.tenant,)).fetchone()
            if count>MAX_NODES or size>MAX_STORAGE: raise IntegrityError('graph capacity exceeded')
            nr=db.execute('SELECT id,body,mac FROM nodes WHERE tenant=? ORDER BY id LIMIT ?',(self.tenant,MAX_NODES+1)).fetchall()
            er=db.execute('SELECT src,relation,dst,mac FROM edges WHERE tenant=? ORDER BY src,relation,dst LIMIT ?',(self.tenant,MAX_EDGES+1)).fetchall()
        if len(nr)>MAX_NODES or len(er)>MAX_EDGES: raise IntegrityError('graph capacity exceeded')
        nodes={i:self._decode(i,body,mac) for i,body,mac in nr}
        adj={i:[] for i in nodes}
        for a,r,b,mac in er:
            if a not in nodes or b not in nodes or r not in RELATIONS or not isinstance(mac,str) or not hmac.compare_digest(mac,self._sign('edge',a,r,b)):
                raise IntegrityError('edge authentication failed')
            adj[a].append((b,r,'out'));adj[b].append((a,r,'in'))
        return nodes,adj

    def retrieve(self,query, *, limit=8,hops=2):
        if type(query) is not str or not 1<=len(query)<=1024 or type(limit) is not int or not 1<=limit<=32 or type(hops) is not int or not 0<=hops<=3:
            raise ValueError('retrieval bounds')
        q=tokens(query)
        if not q: return []
        nodes,adj=self.snapshot()
        # Deterministic lexical seed ranking, then bounded provenance traversal.
        direct=[]
        for i,n in nodes.items():
            terms=tokens(n['text']); overlap=len(q&terms)
            if overlap: direct.append((i,overlap/len(q)))
        direct.sort(key=lambda v:(-v[1],v[0]));direct=direct[:limit]
        return self.expand(nodes,adj,direct,limit=limit,hops=hops)

    @staticmethod
    def expand(nodes,adj,direct, *, limit,hops):
        result=[];visited={i for i,_ in direct};queue=deque()
        for i,score in direct: queue.append((i,score,[i],[]))
        while queue and len(result)<limit:
            i,score,path,relations=queue.popleft()
            result.append({'id':i,**nodes[i],'score':score,'path':path,'relations':relations})
            if len(path)-1<hops:
                for j,r,d in sorted(adj[i]):
                    if j not in visited:
                        visited.add(j);queue.append((j,score/2,path+[j],relations+[{'relation':r,'direction':d}]))
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True,type=Path);p.add_argument('--key-file',required=True,type=Path);p.add_argument('--tenant',required=True);p.add_argument('--query',required=True);a=p.parse_args()
    with a.key_file.open('rb') as f: key=f.read(4097)
    print(json.dumps(GraphMemory(a.db,key,a.tenant).retrieve(a.query),indent=2,allow_nan=False))


if __name__=='__main__': main()
