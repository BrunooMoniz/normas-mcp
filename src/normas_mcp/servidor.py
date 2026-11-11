"""Servidor MCP (stdio) das normas brasileiras sobre prestadoras de serviços de ativos virtuais (PSAV).

Devolve o artigo, a fonte oficial e a situação de vigência de cada norma do Banco Central, do CMN e da CVM.
O índice (dados/psav.json.gz) sai dos acervos públicos normas-bcb e normas-cvm, por scripts/montar_indice.py.
A busca é por palavras (BM25), sem IA e sem rede: quem interpreta é o assistente que chama as ferramentas.
"""
import collections
import functools
import gzip
import json
import math
import re
import unicodedata
from importlib.resources import files

from mcp.server import MCPServer

AVISO = ("Aviso: texto informativo, convertido dos portais do BCB e da CVM; não substitui a publicação oficial. "
         "Confira a fonte oficial antes de citar.")
mcp = MCPServer("normas-psav", instructions=(
    "Normas do Banco Central, do CMN e da CVM sobre prestadoras de serviços de ativos virtuais (PSAV), criptoativos e "
    "o que elas citam ou alteram. Use `buscar` para achar o artigo, `norma` para ver uma norma, quem a alterou ou "
    "revogou e ler um artigo, e `panorama` para a lista das normas do tema. Toda resposta traz a situação de vigência: "
    "nunca apresente como vigente uma norma marcada como REVOGADA. Leis e decretos aparecem só com o link."))

VAZIAS = set("a o e de do da dos das em no na nos nas um uma para por com que se ao aos as os ou como sobre qual quais "
             "quando onde quem sao ser pode podem deve devem ha tem pelo pela entre".split())
# o que as pessoas perguntam -> como a norma escreve
SINONIMOS = {"psav": "prestadora servico ativo virtual", "psavs": "prestadora servico ativo virtual",
             "cripto": "ativo virtual criptoativo", "criptoativo": "ativo virtual", "criptoativos": "ativo virtual",
             "criptomoeda": "ativo virtual criptoativo", "criptomoedas": "ativo virtual criptoativo",
             "exchange": "prestadora servico ativo virtual intermediaria", "bitcoin": "ativo virtual criptoativo"}
ABREVIADOS = {"res": "resolucao", "circ": "circular", "in": "instrucao normativa", "inst": "instrucao"}
K1, B = 1.5, 0.75
POR_NORMA = 3  # trechos da mesma norma numa resposta, para uma norma longa não tomar a lista toda


def plano(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def radical(p):
    # shortcut: só plural; trocar por um stemmer de verdade se a busca errar por flexão de verbo
    for fim, troca in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ois", "ol"), ("ns", "m"),
                       ("res", "r"), ("zes", "z"), ("s", "")):
        if len(p) > len(fim) + 2 and p.endswith(fim):
            return p[:-len(fim)] + troca
    return p


def termos(texto):
    return [radical(p) for p in re.findall(r"[a-z0-9]+", plano(texto)) if p not in VAZIAS and len(p) > 1]


def chave(texto):
    """Palavras que identificam uma norma: 'Res. BCB nº 520/2025' -> {'resolucao', 'bcb', '520', '2025'}."""
    t = re.sub(r"(?<=\d)\.(?=\d)", "", plano(texto))
    return {q for p in re.findall(r"[a-z0-9]+", t) if p not in ("n", "no", "nos", "ns", "de")
            for q in ABREVIADOS.get(p, p).split()}


@functools.cache
def indice():
    d = json.loads(gzip.decompress((files("normas_mcp") / "dados" / "psav.json.gz").read_bytes()))
    listas, tamanhos = collections.defaultdict(list), []
    for n, (i, rotulo, texto) in enumerate(d["trechos"]):
        norma = d["normas"][i]
        conta = collections.Counter(termos(f"{norma['titulo']} {norma['ementa']} {rotulo} {texto}"))
        tamanhos.append(sum(conta.values()))
        for termo, vezes in conta.items():
            listas[termo].append((n, vezes))
    d["listas"], d["tamanhos"], d["media"] = listas, tamanhos, sum(tamanhos) / max(1, len(tamanhos))
    d["rotulos"] = collections.defaultdict(list)
    for n, (i, rotulo, _) in enumerate(d["trechos"]):
        d["rotulos"][i].append(n)
    return d


def nomes(ids, d, limite=12):
    ids = sorted(ids, key=lambda i: d["nomes"].get(i, i))
    return ", ".join(d["nomes"].get(i, i) for i in ids[:limite]) + (f" e mais {len(ids) - limite}" if len(ids) > limite else "")


def situacao(i, d):
    n = d["normas"][i]
    if n["estado"] == "revogada":
        return "REVOGADA por " + nomes(n["por"], d) if n["por"] else "REVOGADA (o portal não informa por qual norma)"
    if n["estado"] == "alterada":
        return "vigente, alterada por " + nomes(n["por"], d) + " (confira a redação atual na fonte)"
    return "vigente"


def ficha(i, d):
    n = d["normas"][i]
    return (f"Situação: {situacao(i, d)}\nData: {n['data']} | id: {i}\n"
            f"Fonte oficial: {n['fonte']}\nTexto em Markdown: {d['urls'].get(i, '')}")


def pontuar(consulta, d):
    """{trecho: pontos} por BM25. Sobe quem cobre mais palavras da pergunta e a norma do núcleo de PSAV; desce a revogada."""
    pedidas = set(termos(consulta))
    extras = {t for p in re.findall(r"[a-z0-9]+", plano(consulta)) for t in termos(SINONIMOS.get(p, ""))} - pedidas
    total, pontos, cobertas = len(d["trechos"]), collections.defaultdict(float), collections.Counter()
    for termo in pedidas | extras:
        lista = d["listas"].get(termo, [])
        idf = math.log(1 + (total - len(lista) + 0.5) / (len(lista) + 0.5)) * (1 if termo in pedidas else 0.5)
        for n, vezes in lista:
            pontos[n] += idf * vezes * (K1 + 1) / (vezes + K1 * (1 - B + B * d["tamanhos"][n] / d["media"]))
            cobertas[n] += termo in pedidas
    for n in pontos:
        norma = d["normas"][d["trechos"][n][0]]
        pontos[n] *= ((0.4 + 0.6 * cobertas[n] / max(1, len(pedidas))) * (1.25 if norma["nucleo"] else 1)
                      * (0.25 if norma["estado"] == "revogada" else 1))
    return pontos


def achar(consulta, limite=8):
    """Os melhores trechos: [(id da norma, rótulo, texto)]."""
    d = indice()
    pontos, vistos, out = pontuar(consulta, d), collections.Counter(), []
    for n in sorted(pontos, key=lambda n: (-pontos[n], n)):
        i = d["trechos"][n][0]
        if vistos[i] < POR_NORMA:
            vistos[i] += 1
            out.append(tuple(d["trechos"][n]))
        if len(out) >= limite:
            break
    return out


def localizar(identificacao):
    """Ids das normas que batem com um id ('bcb:resolucao-bcb:520') ou com um nome ('Resolução BCB 520')."""
    d = indice()
    if identificacao.strip() in d["normas"]:
        return [identificacao.strip()]
    pedido = chave(identificacao)
    if not pedido:
        return []
    achados = []
    for i, n in d["normas"].items():
        titulo = chave(n["titulo"])
        anos = {n["data"][:4], n["data"][2:4]}  # 'Resolução BCB 520/2025' também vale
        if pedido <= titulo | anos and pedido & titulo:
            achados.append((titulo not in (pedido, pedido - anos), len(titulo), i))
    exatos = [a for a in achados if not a[0]]
    return [a[2] for a in sorted(exatos or achados)]


@mcp.tool()
def buscar(consulta: str, limite: int = 8) -> str:
    """Busca nas normas do BCB, do CMN e da CVM sobre PSAV e ativos virtuais e devolve os artigos mais relevantes.

    Cada resultado traz a norma, o artigo, a situação de vigência (vigente, alterada por, REVOGADA por), a fonte
    oficial e o texto do artigo. A busca é por palavras: use os termos da regulação ("prestadora de serviços de ativos
    virtuais", "capital mínimo", "segregação patrimonial") e refaça com outras palavras se o resultado não servir.
    """
    d = indice()
    achados = achar(consulta, max(1, min(limite, 15)))
    if not achados:
        return "Nada encontrado. Tente outras palavras ou veja a lista das normas com `panorama`."
    return "\n\n---\n\n".join(f"### {d['normas'][i]['titulo']}, {rotulo}\n{ficha(i, d)}\n\n{texto}"
                              for i, rotulo, texto in achados) + f"\n\n---\n{AVISO}"


@mcp.tool()
def norma(identificacao: str, artigo: str = "") -> str:
    """Mostra uma norma: ementa, situação de vigência, quem a alterou ou revogou, o que ela altera, revoga e cita.

    identificacao: o nome ("Resolução BCB 520", "Parecer de Orientação CVM 40") ou o id que `buscar` devolve.
    artigo: opcional; com "4" ou "Art. 4º" devolve o texto desse artigo (em norma com anexos, de todos os que tiverem
    esse número).
    """
    d = indice()
    ids = localizar(identificacao)
    if not ids:
        return f"Não achei a norma '{identificacao}' neste recorte. Use `buscar` ou `panorama` para ver o que há."
    if len(ids) > 1:
        return "Mais de uma norma bate com esse nome; repita com o id:\n" + "\n".join(
            f"- {i}: {d['normas'][i]['titulo']} ({d['normas'][i]['data']})" for i in ids[:15])
    i = ids[0]
    n = d["normas"][i]
    trechos = [d["trechos"][k] for k in d["rotulos"].get(i, [])]
    if artigo:
        num = re.search(r"\d+(?:-[A-Za-z])?", artigo)
        alvo = re.compile(rf"Art\. ?{re.escape(num[0])}[ºo°]?(?![\d-])" if num else re.escape(artigo), re.I)
        achados = [t for t in trechos if alvo.search(t[1])]
        if not achados:
            return f"{n['titulo']} não tem '{artigo}' no índice. {ficha(i, d)}"
        return f"## {n['titulo']}\n{ficha(i, d)}\n\n" + "\n\n".join(f"### {t[1]}\n{t[2]}" for t in achados[:8]) + (
            f"\n\n(e mais {len(achados) - 8} trechos com esse número; diga o anexo)" if len(achados) > 8 else "") + f"\n\n{AVISO}"
    linhas = [f"## {n['titulo']}", n["ementa"], ficha(i, d),
              "Faz parte do núcleo de PSAV." if n["nucleo"] else "Entra como contexto: é citada ou alterada por norma de PSAV."]
    for grupo, rotulos in ((n["entra"], {"revoga": "Revogada por", "revoga_parcial": "Revogada em parte por",
                                         "altera": "Alterada por", "regulamenta": "Regulamentada por",
                                         "conjunta": "Mesma norma no outro acervo"}),
                           (n["sai"], {"revoga": "Revoga", "revoga_parcial": "Revoga em parte", "altera": "Altera",
                                       "regulamenta": "Regulamenta", "cita": "Cita", "conjunta": "Mesma norma no outro acervo"})):
        linhas += [f"{rotulos[r]}: {nomes(ids_, d)}" for r, ids_ in sorted(grupo.items()) if r in rotulos]
    links = sorted({j for g in (n["sai"], n["entra"]) for l in g.values() for j in l if j.split(":")[0] not in ("bcb", "cvm", "ext")})
    linhas += [f"Leis e decretos citados: " + "; ".join(f"{d['nomes'][j]} ({d['urls'][j]})" for j in links if j in d["urls"])] if links else []
    if trechos:
        rotulos = list(dict.fromkeys(re.sub(r" \(parte .*", "", t[1]) for t in trechos))
        linhas.append(f"Trechos ({len(rotulos)}): " + "; ".join(rotulos[:60]) + (" ..." if len(rotulos) > 60 else "")
                      + "\nPara ler um artigo, chame `norma` com o parâmetro artigo.")
    else:
        linhas.append("O texto desta norma não está no índice (norma revogada do contexto); veja o link acima.")
    return "\n\n".join(l for l in linhas if l) + f"\n\n{AVISO}"


@mcp.tool()
def panorama(limite: int = 40) -> str:
    """Lista as normas do núcleo de PSAV em vigor (BCB, CMN e CVM), das que mais tratam do tema para as que menos.

    Bom ponto de partida para "quais normas regem as prestadoras de serviços de ativos virtuais".
    """
    d = indice()
    nucleo = [(i, n) for i, n in d["normas"].items() if n["nucleo"]]
    vivas = sorted((x for x in nucleo if x[1]["estado"] != "revogada"), key=lambda x: (-x[1]["mencoes"], x[0]))
    recente = max(n["data"] for _, n in nucleo)
    cabeca = (f"Recorte de PSAV: {len(nucleo)} normas no núcleo ({len(vivas)} em vigor) e "
              f"{len(d['normas']) - len(nucleo)} de contexto. Norma mais recente do núcleo: {recente}.")
    itens = [f"- {n['titulo']} ({n['data']}, {situacao(i, d)}; id {i}): {n['ementa'][:220]}"
             for i, n in vivas[:max(1, min(limite, 150))]]
    return "\n".join([cabeca, ""] + itens + ["", AVISO])


def main():
    mcp.run()


if __name__ == "__main__":
    main()
