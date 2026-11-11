# normas-mcp

Servidor MCP com as normas brasileiras sobre **prestadoras de serviços de ativos virtuais (PSAV)**: Banco Central, CMN
e CVM. O assistente pergunta, e recebe o artigo, a fonte oficial e a situação de vigência da norma (vigente, alterada
ou revogada, e por qual).

Roda na sua máquina, sem servidor, sem conta e sem chave. Os textos vêm dos acervos públicos
[normas-bcb](https://github.com/BrunooMoniz/normas-bcb) e [normas-cvm](https://github.com/BrunooMoniz/normas-cvm).

> [!IMPORTANT]
> Os textos têm caráter informativo e **não substituem a publicação oficial**. São conversões automáticas dos portais
> do BCB e da CVM. Confira sempre a fonte indicada em cada resposta antes de citar.

## Instalar pedindo ao seu agente

Copie o texto abaixo e mande para o seu agente (Claude Code, Codex, Cursor ou outro que rode comandos na sua
máquina). Ele instala o que faltar, registra o servidor e testa.

```text
Configure para mim o servidor MCP "normas-psav", com as normas do Banco Central, do CMN e da CVM sobre
prestadoras de serviços de ativos virtuais (PSAV). Repositório: https://github.com/BrunooMoniz/normas-mcp

1. Confira se o uv está instalado (uv --version). Se não estiver, instale pelo método oficial em
   https://docs.astral.sh/uv/getting-started/installation/ e me avise do que instalou.

2. Baixe o servidor e confirme que ele sobe sem erro. Com a entrada vazia ele termina sozinho:
   uvx --from git+https://github.com/BrunooMoniz/normas-mcp normas-mcp < /dev/null

3. Registre o servidor no cliente em que você está rodando, valendo para todos os meus projetos:
   - Claude Code:
     claude mcp add --scope user normas-psav -- uvx --from git+https://github.com/BrunooMoniz/normas-mcp normas-mcp
   - Codex:
     codex mcp add normas-psav -- uvx --from git+https://github.com/BrunooMoniz/normas-mcp normas-mcp
   - Claude Desktop, Cursor ou outro cliente com arquivo de configuração: acrescente em "mcpServers" a entrada
     "normas-psav" com "command": "uvx" e
     "args": ["--from", "git+https://github.com/BrunooMoniz/normas-mcp", "normas-mcp"].
     Não apague nem altere o que já existe no arquivo.

4. Confira que o servidor aparece na lista de MCPs do cliente e me diga se preciso reiniciar o aplicativo ou
   abrir uma conversa nova para as ferramentas buscar, norma e panorama aparecerem.

5. Quando elas estiverem disponíveis, teste com a pergunta "quais são as modalidades de prestadora de serviços
   de ativos virtuais?" e me mostre a norma, o artigo e a situação de vigência que vieram na resposta.

Não precisa de conta, chave nem servidor: tudo roda na minha máquina. Se algum passo falhar, pare e me mostre
o erro em vez de tentar outro caminho.
```

## Instalar à mão

Precisa do [uv](https://docs.astral.sh/uv/getting-started/installation/). O comando do servidor é um só:

```
uvx --from git+https://github.com/BrunooMoniz/normas-mcp normas-mcp
```

**Claude Code**

```
claude mcp add --scope user normas-psav -- uvx --from git+https://github.com/BrunooMoniz/normas-mcp normas-mcp
```

**Claude Desktop, Cursor e outros clientes com arquivo de configuração**

```json
{
  "mcpServers": {
    "normas-psav": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/BrunooMoniz/normas-mcp", "normas-mcp"]
    }
  }
}
```

**Codex**

```
codex mcp add normas-psav -- uvx --from git+https://github.com/BrunooMoniz/normas-mcp normas-mcp
```

Para pegar as normas novas, rode uma vez com `--refresh`:

```
uvx --refresh --from git+https://github.com/BrunooMoniz/normas-mcp normas-mcp
```

## Ferramentas

| Ferramenta | O que faz |
| --- | --- |
| `buscar` | Acha os artigos mais relevantes para uma pergunta, com norma, situação de vigência, fonte oficial e texto. |
| `norma` | Mostra uma norma: ementa, vigência, quem a alterou ou revogou, o que ela altera, revoga e cita. Com `artigo`, devolve o texto do artigo. |
| `panorama` | Lista as normas do núcleo de PSAV em vigor. |

Exemplos de pergunta: "quais são as modalidades de PSAV?", "qual o capital mínimo de uma prestadora de serviços de
ativos virtuais?", "fundo de investimento pode comprar criptoativo?", "quando um token é valor mobiliário?".

## O que entra

O recorte é feito sem IA, por `scripts/montar_indice.py`:

- **Núcleo:** normas cujo texto fala de ativos virtuais, criptoativos ou PSAV.
- **Contexto:** normas que o núcleo cita, altera, revoga ou regulamenta, e as que alteram ou revogam o núcleo. As
  relações vêm do grafo publicado em cada acervo (`grafo/arestas.jsonl`).
- Norma revogada do contexto entra só com os metadados, para o servidor poder dizer quem a revogou.
- Cada norma é quebrada por artigo. Texto sem artigos (ofícios, pareceres) vai por parágrafos.

A busca é por palavras (BM25), sem IA e sem rede: quem interpreta a pergunta é o assistente. Normas do núcleo sobem
na ordem e normas revogadas descem.

## Limites

- Leis e decretos (a Lei nº 14.478/2022, por exemplo) aparecem só como link para o
  [ctresb/leis](https://github.com/ctresb/leis); o texto delas não está no índice.
- A situação de vigência vem dos portais oficiais e do grafo dos acervos. Norma "alterada" traz o texto como o portal
  publica; confira a redação atual na fonte.
- O índice é refeito uma vez por dia. Norma publicada hoje pode levar um dia para aparecer.

## Desenvolvimento

```
python3 scripts/montar_indice.py --bcb ../normas-bcb --cvm ../normas-cvm   # refaz o índice
uv run python -m unittest discover -s tests                                # testes, pelo protocolo MCP
```

Licença MIT para o código. As normas são atos oficiais, de domínio público.
