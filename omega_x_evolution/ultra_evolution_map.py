"""Maintainer-supplied L12–L111 planning registry; never a promotion authority."""
from __future__ import annotations

from dataclasses import dataclass

CANONICAL_BASE_GIT_SHA = '5e24375d6e77835e7752f6ef4d489d38b4850b23'
MAP_RELEASE_DATE = '2026-11-21'
BINDING = 'BINDING_ROADMAP'
PROPOSED = 'PROPOSED_NON_BINDING'


@dataclass(frozen=True, slots=True)
class LevelSpec:
    level_id: str
    epoch_id: str
    title: str
    governance_status: str
    dependencies: tuple[str, ...]
    legacy_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PackageSpec:
    package_id: str
    level_id: str
    phase_index: str
    phase: str
    governance_status: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CrossDependency:
    source: str
    target: str
    shared_contract: str


# Epoch ID, first/last level, title, domain.
EPOCHS = (
    ('E01','L12','L21','Fundamenty zaufania i niezawodny runtime','TRUST/RUNTIME'),
    ('E02','L22','L31','Silnik ewolucyjnego odkrywania algorytmow','EVOLUTION/SEARCH'),
    ('E03','L32','L41','Pamiec, pochodzenie wiedzy i epistemika','MEMORY/EPISTEMICS'),
    ('E04','L42','L51','Rozumowanie, przyczynowosc i wspolpraca agentow','COGNITION/AGENTS'),
    ('E05','L52','L61','Swiadomosc sprzetu, fizyka kosztow i energia','HARDWARE/ENERGY'),
    ('E06','L62','L71','Federacja, prywatnosc i odpornosc rozproszona','FEDERATION/SRE'),
    ('E07','L72','L81','Formalna synteza i niezalezna weryfikacja','FORMAL/COMPILERS'),
    ('E08','L82','L91','Metoda naukowa i odkrycia algorytmiczne','SCIENCE/EVIDENCE'),
    ('E09','L92','L101','Multimodalnosc i produkty generatywne','BUILDERS/MEDIA'),
    ('E10','L102','L111','Metaewolucja z kontrola korzenia zaufania','OPEN_ENDED/GOVERNANCE'),
)
# Exact level IDs, supplied titles, direct prerequisites, legacy references.
_RAW = '''12|Dowodowa integracja L12||L11,v72-v75,v81-v87
13|Natywna magistrala Rust / Zenoh / WASI|12|L10 v66,v81
14|Zewnetrzna kotwica monotoniczna|12,13|L10 XFAIL
15|Hermetyczny lancuch dostaw|12,14|
16|Regresje wydajnosci z korekta szumu|12|v21
17|SLO i obserwowalnosc generacji|13,16|
18|Izolacja wykonania zero-trust|13,14,17|
19|Aktorowy archipelag MAP-Elites|15,18|v22
20|Ewolucyjny dziennik zdarzen|14,19|
21|Odpornosc end-to-end na katastrofy|18,20|
22|Selekcja Pareto pod ograniczeniami|19,21|
23|Przyczynowe wyjasnianie ulepszen|16,22|v55
24|Adaptacyjne nisze topologiczne|22,23|v23
25|Modele srodowisk ewolucji|23,24|
26|Zespol mutatorow z budzetem|22,25|
27|Kompilator kandydatow AST/IR|18,26|
28|Rownowaznosciowa optymalizacja e-graph|27|v64
29|Proof-carrying mutation|28,14|
30|Metaoptymalizacja kosztu eksploracji|16,26,29|
31|Preregistracja eksperymentow ewolucyjnych|23,30|
32|Pamiec z pochodzeniem dowodu|20,31|
33|Wieloczasowy model wiedzy|32|v52
34|Kontrolowana pamiec asocjatywna|32|v25
35|Pamiec wielohoryzontowa|33,34|
36|GraphRAG z semantyka i dowodami|32,35|
37|Konsolidacja pamieci bez utraty faktow|33,36|
38|Uczenie lokalne z wersjami adapterow|30,37|v34
39|Kontrfaktyczna historia wiedzy|33,38|v55
40|Kalibracja epistemiczna pamieci|36,39|
41|Prawo do usuniecia i slad audytu|35,40|
42|Kompilator grafow rozumowania|27,36|
43|Niezalezny Critic/Verifier|29,42|
44|Causal policy engine|39,43|
45|Planowanie wielohoryzontowe|25,44|
46|OOD i introspekcja niepewnosci|40,45|
47|Adwersarialna recenzja kandydatow|43,46|
48|Protokol wspolpracy agentow|18,47|
49|Negocjacja pracy i konsensusu|19,48|
50|Funkcjonalny model wlasnego stanu|46,49|
51|Benchmark wspolpracy wieloagentowej|47,50|
52|Katalog sprzetu i wlasnosci|17,31|
53|Heterogeniczny scheduler|30,52|
54|Zarzadca KV-cache i pamieci|35,53|
55|Streaming inference z kontrola ogona|16,54|
56|Pelna ksiega energii systemowej|52,55|v68-v69,v83
57|FeRAM/ReRAM jako trwale peryferia|14,56|v70
58|Granice obliczen kwantowych|31,56|v27
59|Compute-in-Memory w cyfrowym blizniaku|56,57|
60|Sprawdzalne jadra RTL/FPGA|29,59|v87
61|Pareto sprzetowo-energetyczne|53,58,60|v71
62|Federacja podpisanych wynikow|20,61|
63|Tozsamosci i odwolania w federacji|14,62|
64|Federacja zachowujaca prywatnosc|41,63|
65|Proweniencja miedzy klastrami|15,62|
66|WAN i rozproszone odtwarzanie|19,65|
67|Bezpieczenstwo BFT bez nieuprawnionych obietnic|14,66|
68|Suwerennosc danych i polityki tenantow|41,67|
69|Tryb offline-first na wielu lokalizacjach|65,68|
70|Wymiana elit bez transferu sekretow|62,69|
71|Federacyjny nadzor nad zmianami|67,70|
72|Kernel-checked dowody arytmetyki|29,60|
73|Pelna tozsamosc bitowa transformacji|27,72|
74|Niezalezne portfolio dowodow|43,73|
75|Hipotezy nowych praw algebraicznych|28,74|v33
76|Counterexample-Guided Synthesis|75|
77|Walidacja numeryczna z przedzialami|61,76|
78|Dowody nieinterferencji wielu sladow|18,74|v86
79|Weryfikacja zmian architektury|28,78|
80|Proof-aware optymalizacja jader|73,79|
81|Trwaly transfer certyfikowanej wiedzy|75,80|
82|Naukowy projekt eksperymentu|31,81|
83|Rejestr benchmarkow i replikacji|16,82|
84|Laboratorium eksperymentow przyczynowych|44,83|
85|Odkrywanie konstrukcji matematycznych|76,84|
86|Identyfikacja dynamiki SINDy|77,85|
87|Model-driven digital twins|59,86|
88|Niepewnosc wniosku eksperymentalnego|82,87|
89|Odkrywanie nowosci z recenzja|47,88|
90|Wieloosrodkowe kampanie powtarzalne|71,89|
91|Publikowalny lancuch naukowego dowodu|83,90|
92|Wizja i przetwarzanie obrazu|53,91|
93|Produkcja i edycja wideo|55,92|
94|Speech, muzyka i dzwiek|41,93|
95|Spojna pamiec multimodalna|36,94|
96|Game Builder narracyjny|42,95|
97|App Builder Code / No-Code|27,96|
98|IDE z agentowa analiza kodu|18,97|
99|Wieloplatformowe wydania natywne|15,98|
100|HITL dla decyzji o wysokiej wadze|71,99|
101|Bezpieczna eksploatacja ekosystemu|17,100|
102|Model umiejetnosci ewolucji|51,101|
103|Ewolucja operatorow tworzenia hipotez|31,102|
104|Adaptacyjna alokacja eksperymentow|30,103|
105|Wielo-kryterialna ekonomia postepu|61,104|
106|Audit of the auditor|43,74,105|
107|Kontrolowana ewolucja architektury systemu|79,106|
108|Koewolucja domen z zabezpieczeniami|70,107|
109|Odpornosc wiedzy na wieloletnie zmiany|57,81,108|
110|Audyt generacyjny i falsyfikacja|90,106,109|
111|Horyzont OMEGA-X: otwarta ewolucja|101,102,110|'''


def _ids(numbers: str) -> tuple[str, ...]:
    return tuple('L'+x for x in numbers.split(',') if x)


def _level(line: str) -> LevelSpec:
    number, title, deps, legacy = line.split('|')
    n = int(number)
    return LevelSpec('L'+number, f'E{(n-12)//10+1:02}', title,
                     BINDING if n == 12 else PROPOSED, _ids(deps),
                     tuple(x for x in legacy.split(',') if x))


LEVELS = tuple(_level(line) for line in _RAW.splitlines())
CROSS_DEPENDENCIES = tuple(CrossDependency(f'L{a}',f'L{b}',contract) for a,b,contract in (
    (12,13,'ABI / bridge'),(14,57,'anti-rollback'),(16,55,'p95/p99'),
    (20,62,'event provenance'),(22,61,'Pareto'),(29,74,'proof carrying'),
    (31,82,'preregistration'),(32,95,'multimodal provenance'),(41,64,'privacy'),
    (43,106,'independent scorer'),(53,92,'hardware scheduler'),(60,73,'RTL/LEC'),
    (71,100,'approval'),(81,109,'proof longevity'),(91,110,'reproducibility'),
    (101,111,'end-to-end governance'),
))
CRITICAL_SECURITY_PATH = _ids('14,18,29,43,74,106')
TRACKS = tuple((tid, domain, _ids(chain), goal) for tid,domain,chain,goal in (
    ('A','TRUST','12,13,14,18,29,43,74,106','Secure promotion and fixed verifier'),
    ('B','REPLAY','15,20,21,31,65,91,110','Reproducibility and recovery'),
    ('C','EVOLUTION','19,22,24,26,28,76,103','Measured algorithmic progress'),
    ('D','MEMORY','32,33,34,36,41,95,109','Provenance, learning and persistence'),
    ('E','HARDWARE','52,53,56,57,59,60,61','Cost, throughput and substrate verification'),
    ('F','FEDERATION','62,63,66,67,69,70,71','Consistency and instance sovereignty'),
    ('G','SCIENCE','44,77,82,84,86,88,91','Scientific method'),
    ('H','PRODUCT','92,93,94,96,97,99,101','Real builds and E2E'),
))
INVARIANTS = tuple((f'INV-{i:02}', rule) for i,rule in enumerate((
    'Fixed evaluator','Least privilege and isolation','Evidence before PASS',
    'No holdout leakage','Distinguish model from hardware','Record and replay',
    'Explicit cost units','No unproved computational advantage','Git main only',
    'Falsifiability','No self-approval','Licensing and data protection',
),1))
GATES = tuple((f'GATE-{i:02}', rule) for i,rule in enumerate((
    'Requirements and sources','Architecture','Implementation completeness',
    'Deterministic tests','Integration and E2E','Security','Recovery',
    'Documentation and evidence','Final acceptance from GATE-01..08',
),1))
_PHASES = ('01/SPEC','02/BUILD','03/TEST','04/GATE')
_STATUSES = frozenset({'PASS','FAIL','BLOCKED','UNKNOWN','NOT_APPLICABLE','OPEN'})


def get_level(level_id: str) -> LevelSpec:
    if type(level_id) is str:
        for level in LEVELS:
            if level.level_id == level_id:
                return level
    raise KeyError('unknown canonical level')


def _graph(levels: tuple[LevelSpec, ...], cross: tuple[CrossDependency, ...]) -> dict[str, set[str]]:
    if type(levels) is not tuple or len(levels) != 100 or any(type(x) is not LevelSpec for x in levels):
        raise ValueError('exactly 100 typed levels required')
    if tuple(x.level_id for x in levels) != tuple(f'L{n}' for n in range(12,112)):
        raise ValueError('level sequence mismatch')
    graph = {x.level_id:set() for x in levels}
    for i, level in enumerate(levels):
        if (level.epoch_id != f'E{i//10+1:02}' or not level.title
                or level.governance_status != (BINDING if i == 0 else PROPOSED)
                or type(level.dependencies) is not tuple
                or len(set(level.dependencies)) != len(level.dependencies)):
            raise ValueError('invalid level metadata')
        for dep in level.dependencies:
            if dep not in graph or dep == level.level_id:
                raise ValueError('unknown dependency or self edge')
            graph[level.level_id].add(dep)
    if type(cross) is not tuple or len(cross) != 16 or any(type(x) is not CrossDependency for x in cross):
        raise ValueError('exactly 16 typed cross dependencies required')
    pairs = set()
    for edge in cross:
        pair = edge.source, edge.target
        if (edge.source not in graph or edge.target not in graph or edge.source == edge.target
                or pair in pairs or not edge.shared_contract):
            raise ValueError('invalid cross dependency')
        pairs.add(pair)
        graph[edge.target].add(edge.source)
    return graph


def _topo(graph: dict[str, set[str]]) -> tuple[str, ...]:
    active, done, ordered = set(), set(), []
    def visit(node: str) -> None:
        if node in active:
            raise ValueError('dependency cycle detected')
        if node in done:
            return
        active.add(node)
        for dep in sorted(graph[node]):
            visit(dep)
        active.remove(node)
        done.add(node)
        ordered.append(node)
    for node in graph:
        visit(node)
    return tuple(ordered)


def _packages(levels: tuple[LevelSpec, ...], graph: dict[str, set[str]], order: tuple[str, ...]) -> tuple[PackageSpec, ...]:
    index = {x.level_id:x for x in levels}
    result = []
    for lid in order:
        for i, phase in enumerate(_PHASES):
            deps = ((f'{lid}-{_PHASES[i-1]}',) if i else
                    tuple(f'{dep}-04/GATE' for dep in sorted(graph[lid])))
            result.append(PackageSpec(f'{lid}-{phase}',lid,phase[:2],phase[3:],index[lid].governance_status,deps))
    return tuple(result)


def generate_400_packages() -> tuple[PackageSpec, ...]:
    graph = _graph(LEVELS,CROSS_DEPENDENCIES)
    return _packages(LEVELS,graph,_topo(graph))


def validate_dag(*, levels: tuple[LevelSpec, ...] = LEVELS,
                 cross_dependencies: tuple[CrossDependency, ...] = CROSS_DEPENDENCIES) -> dict:
    graph = _graph(levels,cross_dependencies)
    order = _topo(graph)
    packages = _packages(levels,graph,order)
    seen = set()
    for package in packages:
        if package.package_id in seen or not set(package.dependencies) <= seen:
            raise ValueError('package graph invalid')
        seen.add(package.package_id)
    if len(seen) != 400:
        raise ValueError('package count mismatch')
    if any(lid not in graph for _,_,chain,_ in TRACKS for lid in chain):
        raise ValueError('unknown track level')
    if any(lid not in graph for lid in CRITICAL_SECURITY_PATH):
        raise ValueError('unknown security path level')
    return {'status':'PASS','base_git_sha':CANONICAL_BASE_GIT_SHA,
            'epochs':len(EPOCHS),'levels':len(levels),'packages':len(packages),
            'binding_levels':sum(x.governance_status == BINDING for x in levels),
            'proposed_levels':sum(x.governance_status == PROPOSED for x in levels),
            'tracks':len(TRACKS),'cross_dependencies':len(cross_dependencies),
            'invariants':len(INVARIANTS),'gates':len(GATES),'cycles_found':0,
            'topological_length':len(order),'release_authorized':False}


def evaluate_dependency_readiness(level_id: str, level_statuses: dict[str,str]) -> dict:
    """Planning only: caller-declared statuses cannot authorize a release."""
    get_level(level_id)
    graph = _graph(LEVELS,CROSS_DEPENDENCIES)
    if (type(level_statuses) is not dict or len(level_statuses) > 100
            or any(type(k) is not str or k not in graph or type(v) is not str or v not in _STATUSES
                   for k,v in level_statuses.items())):
        raise ValueError('invalid planning statuses')
    pending = list(graph[level_id])
    ancestors = set()
    while pending:
        node = pending.pop()
        if node not in ancestors:
            ancestors.add(node)
            pending.extend(graph[node])
    blocking = [{'dependency':dep,'status':level_statuses.get(dep,'OPEN')}
                for dep in sorted(ancestors,key=lambda x:int(x[1:]))
                if level_statuses.get(dep,'OPEN') != 'PASS']
    return {'level_id':level_id,'ready':not blocking,'status':'BLOCKED' if blocking else 'READY',
            'blocking_dependencies':blocking,'planning_only':True,'release_authorized':False}
