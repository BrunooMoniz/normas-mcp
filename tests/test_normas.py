"""Testes do servidor pelo protocolo MCP (stdio), como um assistente o usa. Rodar: uv run python -m unittest discover -s tests"""
import re
import sys
import unittest
from pathlib import Path

from mcp import Client, StdioServerParameters

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import montar_indice  # noqa: E402
from normas_mcp import servidor  # noqa: E402

# pergunta, normas que respondem (qualquer uma serve) e, quando há um artigo certo, o artigo
PERGUNTAS = [
    ("Quais são as modalidades de sociedade prestadora de serviços de ativos virtuais?", ["bcb:resolucao-bcb:520"], ["Art. 4º"]),
    ("Qual o limite mínimo de capital social e de patrimônio líquido de uma PSAV?",
     ["bcb:resolucao-bcb:517", "bcb:resolucao-conjunta:14"], []),
    ("Como é o processo de autorização para funcionamento de uma sociedade prestadora de serviços de ativos virtuais?",
     ["bcb:resolucao-bcb:519"], []),
    ("Pagamento ou transferência internacional com ativos virtuais entra no mercado de câmbio?",
     ["bcb:resolucao-bcb:521"], ["Art. 76-A"]),
    ("O que é stablecoin, o ativo virtual referenciado em moeda fiduciária?", ["bcb:resolucao-bcb:520"], ["Art. 2º"]),
    ("Como deve ser a segregação patrimonial entre os ativos virtuais da prestadora e os dos clientes?",
     ["bcb:resolucao-bcb:520"], ["Art. 30"]),
    ("Fundo de investimento pode investir em criptoativos?", ["cvm:resolucao:175", "cvm:oficio-circular-sin:11-2018"], []),
    ("Quando um token é considerado valor mobiliário?", ["cvm:parecer-de-orientacao:40"], []),
    ("Tokens de recebíveis ou de renda fixa são valores mobiliários?", ["cvm:oficio-circular-sse:4-2023"], []),
    ("Qual o prazo para a prestadora de serviços de ativos virtuais que já está em atividade solicitar autorização?",
     ["bcb:resolucao-bcb:520"], ["Art. 88", "Art. 22"]),
    ("Que informações sobre operações com ativos virtuais no mercado de câmbio devem ser remetidas ao Banco Central?",
     ["bcb:instrucao-normativa-bcb:693"], []),
    ("Quais os critérios contábeis para reconhecimento e mensuração de ativos virtuais?",
     ["bcb:resolucao-cmn:5281", "bcb:resolucao-bcb:550"], []),
]


def sessao():
    return Client(StdioServerParameters(command=sys.executable, args=["-m", "normas_mcp.servidor"]))


class PeloProtocolo(unittest.IsolatedAsyncioTestCase):
    async def chamar(self, cliente, ferramenta, **argumentos):
        r = await cliente.call_tool(ferramenta, argumentos)
        self.assertFalse(r.is_error, r.content)
        return r.content[0].text

    async def test_ferramentas(self):
        async with sessao() as c:
            nomes = {t.name for t in (await c.list_tools()).tools}
        self.assertEqual(nomes, {"buscar", "norma", "panorama"})

    async def test_perguntas_reais_trazem_o_artigo_a_fonte_e_a_vigencia(self):
        async with sessao() as c:
            for pergunta, ids, artigos in PERGUNTAS:
                blocos = (await self.chamar(c, "buscar", consulta=pergunta)).split("\n\n---\n\n")
                certos = [b for b in blocos if any(f"id: {i}\n" in b for i in ids) and (
                    not artigos or any(re.match(rf"### .*, {re.escape(a)}(?: \(parte|\n)", b) for a in artigos))]
                self.assertTrue(certos, f"{pergunta} -> {[b.splitlines()[0] for b in blocos]}")
                self.assertRegex(certos[0], r"Situação: (vigente|REVOGADA)")
                self.assertRegex(certos[0], r"Fonte oficial: https://(www\.bcb\.gov\.br|conteudo\.cvm\.gov\.br)/")

    async def test_vigencia_diz_quem_alterou_e_quem_revogou(self):
        async with sessao() as c:
            alterada = await self.chamar(c, "norma", identificacao="Res. BCB nº 520/2025")
            self.assertIn("Situação: vigente, alterada por", alterada)
            self.assertIn("Resolução BCB N° 589", alterada)
            self.assertIn("Lei 14.478/2022 (https://github.com/ctresb/leis/blob/main/federal/leis-ordinarias/2022/", alterada)
            revogada = await self.chamar(c, "norma", identificacao="bcb:resolucao-bcb:588")
            self.assertIn("Situação: REVOGADA por Resolução BCB N° 591", revogada)
            # norma revogada do contexto: só metadados, com quem a revogou
            antiga = await self.chamar(c, "norma", identificacao="Instrução CVM 555")
            self.assertIn("Situação: REVOGADA por Resolução CVM 175", antiga)
            self.assertIn("não está no índice", antiga)

    async def test_artigo_de_uma_norma(self):
        async with sessao() as c:
            texto = await self.chamar(c, "norma", identificacao="Resolução BCB 520", artigo="Art. 4º")
            self.assertEqual(re.findall(r"^### (.*)$", texto, re.M), ["Art. 4º"])  # não traz o 40 nem o 41
            self.assertIn("modalidades", texto)
            anexo = await self.chamar(c, "norma", identificacao="Resolução CVM 175", artigo="2")
            self.assertIn("### ANEXO NORMATIVO I, Art. 2º", anexo)

    async def test_nome_ambiguo_ou_desconhecido_nao_inventa(self):
        async with sessao() as c:
            self.assertIn("Mais de uma norma", await self.chamar(c, "norma", identificacao="Resolução 200"))
            self.assertIn("Não achei", await self.chamar(c, "norma", identificacao="Resolução BCB 999999"))
            self.assertIn("Nada encontrado", await self.chamar(c, "buscar", consulta="xyzzyqwerty"))

    async def test_panorama_so_lista_norma_em_vigor(self):
        async with sessao() as c:
            texto = await self.chamar(c, "panorama")
            self.assertIn("- Resolução BCB N° 520 (2025-11-10, vigente, alterada por", texto)
            self.assertNotIn("Resolução BCB N° 588 ", texto)
            self.assertNotIn("REVOGADA", texto)


class Indice(unittest.TestCase):
    def test_quebra_por_artigo(self):
        corpo = ("# Resolução X\n\nEmenta.\n\nANEXO I – SUMÁRIO 12\n\nArt. 1º  Primeiro.\n\n§ 1º  Parágrafo, conforme o\n"
                 "art. 9º da Lei.\n\nArt.\n2º Segundo.\n\nANEXO I\n\n Art. 1º No anexo.\n\n**Art. 2º-A** Outro.\n")
        self.assertEqual([r for r, _ in montar_indice.trechos(corpo)],
                         ["Preâmbulo", "Art. 1º", "Art. 2º", "ANEXO I, Art. 1º", "ANEXO I, Art. 2º-A"])
        self.assertEqual([r for r, _ in montar_indice.trechos("# Ofício\n\nPrezados,\n\ntexto sem artigos.\n")], ["Texto"])
        partes = montar_indice.fatiar("\n\n".join(["palavra " * 100] * 12), 3000)
        self.assertGreater(len(partes), 1)
        self.assertTrue(all(len(p) <= 3000 for p in partes))

    def test_indice_coerente(self):
        d = servidor.indice()
        self.assertGreater(sum(n["nucleo"] for n in d["normas"].values()), 100)
        self.assertTrue(all(i in d["normas"] and len(t) <= montar_indice.TAMANHO for i, _, t in d["trechos"]))
        self.assertTrue(all(n["fonte"].startswith("https://") and n["estado"] in ("vigente", "alterada", "revogada")
                            for n in d["normas"].values()))
        # norma revogada só tem texto se for do núcleo
        com_texto = {i for i, _, _ in d["trechos"]}
        self.assertFalse([i for i in com_texto if d["normas"][i]["estado"] == "revogada" and not d["normas"][i]["nucleo"]])

    def test_nomes(self):
        self.assertEqual(montar_indice.nome_do_id("lei:4595-1964"), "Lei 4.595/1964")
        self.assertEqual(servidor.localizar("Resolução CMN nº 4.966/2021"), ["bcb:resolucao-cmn:4966"])
        self.assertEqual(servidor.localizar("Parecer de Orientação CVM 40"), ["cvm:parecer-de-orientacao:40"])


if __name__ == "__main__":
    unittest.main()
