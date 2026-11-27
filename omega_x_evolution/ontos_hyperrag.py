"""Ephemeral hybrid retrieval over the authorized sealed OTCE view.

No filesystem ingestion, embeddings, generation, or persistent plaintext index.
All content returned is untrusted data, never an instruction or tool grant.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
import re
import sqlite3
import unicodedata

from .ontos_otce import Read, _name, _pin, _int
from .ontos_reversible_ops import OperatorJournal
from .ontos_v72_jcs import canonical_json

DOMAIN=b'OMEGA-X/HyperRAG/v1\x00'


def _tokens(text):
    return re.findall(r'[^\W_]+',unicodedata.normalize('NFC',text.casefold()))


@dataclass(frozen=True,slots=True)
class Search:
    shard: str
    text: str
    limit: int=5

    def __post_init__(self):
        if (not _name(self.shard) or type(self.text) is not str or not _int(self.limit,1,16)
                or not 1<=len(self.text)<=256):
            raise ValueError('bounded search required')
        try:
            size=len(self.text.encode('utf-8'))
        except UnicodeError as exc:
            raise ValueError('invalid query unicode') from exc
        if size>256 or not 1<=len(_tokens(self.text))<=32:
            raise ValueError('bounded query bytes and tokens')


def search_key(format_pin,s):
    """Bind exact text, shard, limit and vault identity inside signed Read.key."""
    if not _pin(format_pin) or type(s) is not Search: raise ValueError('typed search and format pin required')
    s.__post_init__()
    return sha256(DOMAIN+canonical_json([format_pin,s.shard,s.text,s.limit])).hexdigest()


def _grams(tokens):
    return Counter(word[i:i+3] for word in tokens for i in range(len(word)-2))


def _cosine(a,b):
    norm=sqrt(sum(x*x for x in a.values())*sum(x*x for x in b.values()))
    return sum(x*b[k] for k,x in a.items())/norm if norm else 0.


@dataclass(frozen=True,slots=True)
class Citation:
    ident: str
    source_sha256: str
    output_sha256: str
    transaction: int
    observed: int
    origin_evolution: int
    view_evolution: int


@dataclass(frozen=True,slots=True)
class Hit:
    citation: Citation
    text: str
    score: float
    lexical: float
    ngram: float
    bm25: float
    graph_support: int
    untrusted: bool=True


def _rank(rows,s,evolution):
    query=_tokens(s.text); qset=set(query); qgrams=_grams(query)
    docs=[_tokens(text) for _,text in rows]
    # FTS input is generated from tokenized text, not user-provided syntax.
    match=' OR '.join('"'+word+'"' for word in sorted(qset))
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute('PRAGMA temp_store=MEMORY')
        db.execute('CREATE VIRTUAL TABLE docs USING fts5(body, tokenize="unicode61 remove_diacritics 0")')
        db.executemany('INSERT INTO docs(rowid,body) VALUES (?,?)',
                       ((i+1,' '.join(words)) for i,words in enumerate(docs)))
        raw={i-1:max(0.,-score) for i,score in db.execute(
            'SELECT rowid,bm25(docs) FROM docs WHERE docs MATCH ?',(match,))}
    peak=max(raw.values(),default=0.)
    relevant={}
    for i,(n,text) in enumerate(rows):
        lexical=len(qset.intersection(docs[i]))/len(qset)
        ngram=min(1.,_cosine(qgrams,_grams(docs[i])))
        bm25=raw.get(i,0.)/peak if peak else 0.
        score=round(.43*lexical+.37*ngram+.20*bm25,12)
        if score>0: relevant[n['id']]=(n,text,score,lexical,ngram,bm25)
    hits=[]
    for ident,(n,text,score,lexical,ngram,bm25) in relevant.items():
        # Only relevant, already authorized same-shard parents contribute.
        support=sum(p in relevant for p in n['parents'])
        citation=Citation(ident,n['source'],n['output'],n['transaction'],n['time']['observed'],
                          n['time']['evolution'],evolution)
        hits.append(Hit(citation,text,score,lexical,ngram,bm25,support))
    hits.sort(key=lambda h:(-h.score,-h.graph_support,-h.citation.observed,-h.citation.transaction,h.citation.ident))
    return tuple(hits[:s.limit])


class HyperRAGJournal(OperatorJournal):
    """Dedicated signed retrieval endpoint; same sealed journal and vault."""
    def search(self,r: Read,s: Search,*,retained,now):
        self._operator(r,'hyperrag')
        if r.key!=search_key(self._state_pin(),s): raise ValueError('search commitment mismatch')
        with self._vault() as db:
            selected,evolution=self._selection(r,retained=retained,now=now)
            rows=[]
            for n in selected:
                if n['kind']=='R0' and n['evidence']=='observed' and n['payload']['key']==s.shard:
                    rows.append((n,self._decrypt(db,n)['value']))
            # Fail closed on FTS5 absence or corruption; no silent fallback.
            return _rank(rows,s,evolution)
