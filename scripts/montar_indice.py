"""Monta o índice do recorte de PSAV (src/normas_mcp/dados/psav.json.gz) a partir dos acervos normas-bcb e normas-cvm.

Recorte, sem IA:
  núcleo    normas cujo texto fala de ativos virtuais, criptoativos ou PSAV;
  contexto  normas que o núcleo cita, altera, revoga ou regulamenta e as que alteram ou revogam o núcleo
            (grafo/arestas.jsonl de cada acervo).
Norma revogada do contexto entra só com os metadados, para o servidor poder dizer quem a revogou.
Uso: python3 scripts/montar_indice.py [--bcb ../normas-bcb] [--cvm ../normas-cvm]
"""
import argparse
import collections
import gzip
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "src" / "normas_mcp" / "dados" / "psav.json.gz"
REPOS = {"bcb": "https://github.com/BrunooMoniz/normas-bcb/blob/main/",
         "cvm": "https://github.com/BrunooMoniz/normas-cvm/blob/main/"}
NUCLEO = re.compile(r"ativos? virtua(?:l|is)|criptoativ|PSAV|criptomoeda|moedas? virtua(?:l|is)", re.I)
# no começo da linha; alguns textos do portal quebram a linha entre 'Art.' e o número
ARTIGO = re.compile(r"^[ \t]*\**(Art\.\s{0,3}\d+[ºo°]?(?:-[A-Z])?)", re.M)
ANEXO = re.compile(r"^[#* ]*(ANEXO(?: NORMATIVO)?(?: [IVXLC\d]+(?:-[A-Z])?)?)\b")
TAMANHO = 3000  # caracteres por trecho: cabe um artigo comum inteiro


def cabecalho(texto):
    """(campos, corpo) de um .md: cada linha do cabeçalho é 'chave: valor em JSON'."""
    if not texto.startswith("---\n"):
        return {}, texto
    fim = texto.find("\n---\n", 4)
    cab = {}
    for linha in texto[4:fim].splitlines():
        k, _, v = linha.partition(": ")
        try:
            cab[k] = json.loads(v) if v[:1] in '"[' else v
        except ValueError:
            cab[k] = v
    return cab, texto[fim + 5:]


def fatiar(texto, limite=TAMANHO):
    """Quebra um texto longo em pedaços de até `limite` caracteres, sempre em fim de parágrafo."""
    partes, atual = [], ""
    for par in re.split(r"\n\s*\n", texto.strip()):
        while len(par) > limite:  # parágrafo sozinho maior que o limite (tabela, texto de PDF sem quebra)
            corte = par.rfind("\n", 0, limite)
            corte = corte if corte > limite // 2 else limite
            partes, atual, par = partes + ([atual] if atual else []) + [par[:corte]], "", par[corte:].lstrip()
        if atual and len(atual) + len(par) + 2 > limite:
            partes, atual = partes + [atual], ""
        atual = f"{atual}\n\n{par}" if atual else par
    return partes + ([atual] if atual.strip() else [])


def trechos(corpo):
    """[(rótulo, texto)]: um trecho por artigo ('Art. 4º', 'ANEXO I, Art. 2º'); texto sem artigos vai por parágrafos."""
    corpo = re.sub(r"^# .*\n", "", corpo.strip(), count=1)  # o título já está nos metadados
    cortes = [m.start() for m in ARTIGO.finditer(corpo)]
    blocos, anexo = [], ""
    for ini, fim in zip([0] + cortes, cortes + [len(corpo)]):
        bloco = corpo[ini:fim].strip()
        if not bloco:
            continue
        m = ARTIGO.match(bloco)
        rotulo = (f"{anexo}, " if anexo and m else "") + (" ".join(m[1].split()) if m else anexo or "Texto")
        if not cortes:
            rotulo = "Texto"
        elif not m:
            rotulo = "Preâmbulo"
        blocos.append((rotulo, bloco))
        for linha in bloco.splitlines() if m else []:  # o anexo anunciado no fim de um artigo vale para os seguintes;
            a = ANEXO.match(linha)                     # o preâmbulo fica de fora: ali os anexos aparecem no sumário
            if a:
                anexo = a[1]
    out = []
    for rotulo, bloco in blocos:
        partes = fatiar(bloco)
        out += [(rotulo if len(partes) == 1 else f"{rotulo} (parte {n} de {len(partes)})", p) for n, p in enumerate(partes, 1)]
    return out


def nome_do_id(i):
    """Nome legível para norma sem arquivo nos acervos: 'lei:4595-1964' -> 'Lei 4.595/1964'."""
    tipos = {"lei": "Lei", "lcp": "Lei Complementar", "ldl": "Lei Delegada", "del": "Decreto-Lei", "dec": "Decreto",
             "mpv": "Medida Provisória"}
    p = i.split(":")
    num, _, ano = p[-1].rpartition("-") if p[0] in tipos or p[0] == "ext" else (p[-1], "", "")
    num = f"{int(num):,}".replace(",", ".") if num.isdigit() else num
    tipo = tipos.get(p[0]) or p[1].replace("-", " ").title().replace("Bcb", "BCB").replace("Cmn", "CMN").replace("Cvm", "CVM")
    return f"{tipo} {num}" + (f"/{ano}" if ano else "")


def montar(pastas):
    estado, arestas, urls, acervo_de = {}, [], {}, {}
    for ac, pasta in pastas.items():
        for e in map(json.loads, (pasta / "grafo" / "estado.jsonl").read_text(encoding="utf-8").splitlines()):
            estado[e["id"]], acervo_de[e["id"]] = e, ac
        arestas += map(json.loads, (pasta / "grafo" / "arestas.jsonl").read_text(encoding="utf-8").splitlines())
        for x in map(json.loads, (pasta / "grafo" / "externos.jsonl").read_text(encoding="utf-8").splitlines()):
            urls.setdefault(x["id"], x["url"])

    def ler(i):
        return (pastas[acervo_de[i]] / estado[i]["caminho"]).read_text(encoding="utf-8")

    mencoes = {i: n for i in estado if (n := len(NUCLEO.findall(ler(i))))}
    contexto = set()
    for a in arestas:
        if a["de"] in mencoes:
            contexto.add(a["para"])
        if a["para"] in mencoes and a["relacao"] != "cita":
            contexto.add(a["de"])
    contexto = {i for i in contexto if i in estado} - set(mencoes)

    sai, entra = collections.defaultdict(dict), collections.defaultdict(dict)
    for a in arestas:
        sai[a["de"]].setdefault(a["relacao"], []).append(a["para"])
        if a["relacao"] != "cita":  # quem cita a norma não muda o que ela vale
            entra[a["para"]].setdefault(a["relacao"], []).append(a["de"])

    normas, pedacos = {}, []
    for i in sorted(set(mencoes) | contexto):
        cab, corpo = cabecalho(ler(i))
        e = estado[i]
        normas[i] = {"titulo": re.sub(r"\s*\(Revogada\)$", "", cab.get("titulo", "")), "data": str(cab.get("data", "")),
                     "ementa": cab.get("ementa", ""), "estado": e["estado"], "por": e["por"], "nucleo": i in mencoes,
                     "mencoes": mencoes.get(i, 0), "fonte": cab.get("fonte", ""), "sai": dict(sai.get(i, {})),
                     "entra": dict(entra.get(i, {}))}
        if i in mencoes or e["estado"] != "revogada":
            pedacos += [[i, rotulo, texto] for rotulo, texto in trechos(corpo)]
    citados = {j for n in normas.values() for grupo in (n["sai"], n["entra"]) for ids in grupo.values() for j in ids}
    nomes = {}
    for j in sorted(citados | set(normas)):
        if j in estado:
            urls[j] = REPOS[acervo_de[j]] + estado[j]["caminho"]
            nomes[j] = normas[j]["titulo"] if j in normas else re.sub(r"\s*\(Revogada\)$", "", cabecalho(ler(j))[0].get("titulo", ""))
        nomes[j] = nomes.get(j) or nome_do_id(j)
    return {"normas": normas, "trechos": pedacos, "nomes": nomes, "urls": {j: u for j, u in sorted(urls.items()) if j in nomes}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bcb", type=Path, default=RAIZ.parent / "normas-bcb")
    ap.add_argument("--cvm", type=Path, default=RAIZ.parent / "normas-cvm")
    a = ap.parse_args()
    indice = montar({"bcb": a.bcb, "cvm": a.cvm})
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SAIDA, "wb") as f, gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as g:  # mtime fixo: saída estável
        g.write(json.dumps(indice, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    n = indice["normas"]
    print(f"{len(n)} normas ({sum(x['nucleo'] for x in n.values())} no núcleo), {len(indice['trechos'])} trechos, "
          f"{SAIDA.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
