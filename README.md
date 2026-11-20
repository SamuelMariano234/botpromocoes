# Hardware Hunter BR

Bot privado para acompanhar ofertas de hardware no Telegram. O núcleo usa regras locais, SQLite e consultas assíncronas; não usa IA paga nem contorna CAPTCHA, login ou mecanismos anti-bot.

## Estado real das integrações

| Fonte | Situação | Observação |
|---|---|---|
| Mercado Livre | Implementada | Usa o endpoint público de busca de catálogo `api.mercadolibre.com/sites/MLB/search`. Limites e disponibilidade são controlados pelo serviço; se mudar, a busca falhará sem bloquear o restante do bot. |
| Amazon Brasil | Desativada | A Product Advertising API requer conta, elegibilidade e credenciais. Não há credenciais fornecidas. |
| Shopee | Desativada | Exige integração autorizada de parceiro; nenhum endpoint privado ou scraping é usado. |
| OLX | Desativada | Não há feed/API de busca autorizada configurada. |

Não se afirma que as fontes desativadas estão monitoradas. Os adaptadores estão isolados para futura integração autorizada. Resultados do Mercado Livre podem não incluir frete, reputação ou todos os campos. “Detectado pelo sistema” é a primeira observação local e não equivale à data de publicação.

## Instalação no Windows

1. Instale Python 3.11 ou superior em [python.org](https://www.python.org/downloads/). Marque **Add Python to PATH** no instalador.
2. Abra PowerShell e confira `py --version` (ou `python --version`).
3. Entre na pasta do projeto: `cd D:\HardwareHunterBR`.
4. Crie e ative o ambiente:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   Se o PowerShell bloquear a ativação, use `\.venv\Scripts\python.exe -m pip install -r requirements.txt` sem ativar.

5. No Telegram, converse com **@BotFather**, envie `/newbot`, escolha nome e usuário e guarde o token em local privado.
6. Descubra seu ID numérico do Telegram (por exemplo, usando @userinfobot). Envie `/start` ao bot criado para abrir a conversa.
7. Copie `.env.example` para `.env` (`Copy-Item .env.example .env`) e preencha `TELEGRAM_BOT_TOKEN` e `AUTHORIZED_USER_IDS`. O ID deve ser numérico; IDs múltiplos podem ser separados por vírgula. Nunca publique o `.env`.
8. Inicie com `python main.py` ou dê duplo clique em `iniciar.bat`. O SQLite é criado automaticamente em `data\hardware_hunter.sqlite3`.
9. Interrompa no terminal com `Ctrl+C`. Para reiniciar, execute o mesmo comando novamente.

## Coleta automática autorizada de grupos Telegram

A Bot API é suficiente para publicar mensagens, mas não fornece acesso completo às mensagens comuns de grupos. Para coleta em tempo real, este projeto usa Telethon/MTProto em uma conta Telegram que já tenha acesso legítimo aos grupos. O coletor não entra em grupos por convite nem contorna privacidade.

1. Acesse [my.telegram.org](https://my.telegram.org), faça login e crie uma aplicação para obter `api_id` e `api_hash`. Essas credenciais são diferentes do token do bot.
2. Guarde-as somente no `.env` como `TELEGRAM_API_ID` e `TELEGRAM_API_HASH`. Nunca as envie em chats ou logs.
3. Inicie o bot publicador em um terminal: `python main.py`.
4. Inicie o coletor em outro terminal: `python collector.py` ou `iniciar_coletor.bat`. Na primeira execução, informe telefone, código de login e senha de verificação em duas etapas se solicitada. A sessão fica em `data/telethon.session`; trate-a como credencial e nunca a compartilhe ou coloque no Git.
5. Na conversa privada com o bot, cadastre cada grupo que sua conta já pode acessar: `/grupo add @username`. Para grupos privados sem username público, use o ID numérico `-100...`; a conta do coletor precisa já ser membro.
6. Adicione o bot publicador ao grupo de destino, conceda permissão para postar e envie `/destino` nele.
7. Use `/grupos` para ver grupos; `/grupo pausar @username`, `/grupo retomar @username` e `/grupo remover @username` para administrar. As mudanças são detectadas pelo coletor em até cerca de um minuto.
8. Configure `/score 70`, `/categorias gpu,cpu,ssd,ram,fonte,monitor,periférico,outros` e, se desejado, `/filtro max 1200` e `/filtro palavra RTX`.

O pipeline persiste origem, ID da mensagem, links, texto, preço, mídia disponível, decisão e justificativa. Preço/link ausentes ou risco elevado vão para `/revisao`; use `/aprovar ID` para liberar manualmente. `/descartadas`, `/publicadas` e `/estatisticas` consultam resultados. O publicador envia imagem local quando conseguiu baixá-la; caso contrário, publica texto e link.

O score da coleta mede principalmente completude/relevância dos dados, não desconto comparado ao mercado. Sem referência verificável não declara que o preço é uma pechincha. A coleta cobre mensagens novas após o processo conectar, não busca histórico antigo. Leia as regras dos grupos e obtenha permissão dos administradores antes de monitorar. O Telethon deve rodar continuamente em separado do bot publicador.

### VPS Linux (systemd)

Rode bot e coletor como dois serviços separados, sob usuário Linux dedicado, com `WorkingDirectory` apontando para a pasta do projeto, `ExecStart` apontando para `.venv/bin/python main.py` e `.venv/bin/python collector.py`, `Restart=on-failure`, e `EnvironmentFile` apontando para `.env` com permissões restritas. O diretório `data/` precisa ser gravável e incluído em backup protegido. Não exponha a sessão MTProto nem copie-a para máquinas não confiáveis.

## Comandos Telegram

- `/start`, `/help`, `/status`, `/config`
- `/pesquisar RTX 3060` busca no Mercado Livre agora.
- `/adicionar RTX 3060 1000` registra produto e preço máximo (opcional); `/remover RTX 3060`; `/watchlist`.
- `/ofertas`, `/achadinhos`, `/ranking`, `/resumo` consultam os anúncios observados.
- `/gpu`, `/cpu`, `/ram`, `/ssd`, `/fontes`, `/mouse`, `/monitor`, `/kits` pesquisam agora; pode-se acrescentar termo ao comando.
- `/historico RTX 3060` e `/precos RTX 3060` mostram estatísticas dos anúncios guardados. A amostra não é série completa nem equivale necessariamente ao mesmo SKU.
- `/favoritos`, botões de favoritar/ignorar, `/pausar`, `/retomar`, `/limpar` (com confirmação).
- Encaminhe manualmente uma mensagem de promoção ao bot: ele tenta ler o preço em formato `R$ ...` e link. Configure `/filtro max 1200` e `/filtro palavra RTX`; `/filtro` mostra os filtros e `/filtro limpar` os remove. Se a oferta passar, o bot responde no privado.
- Para republicar em um grupo seu, adicione o bot ao grupo, conceda permissão para publicar e envie `/destino` dentro dele. Encaminhamentos aprovados são copiados para o grupo com uma mensagem de preço/link. O bot só processa o que você encaminhar diretamente para ele.
- Para monitorar automaticamente novas mensagens de grupos autorizados: adicione o bot ao grupo de origem, envie `/origem` nesse grupo usando sua conta autorizada, e configure o grupo de destino com `/destino`. Para parar a leitura de um grupo, envie `/origem remover` nele. O bot precisa receber as mensagens do grupo: torne-o administrador ou desative Group Privacy no BotFather. O recurso só cobre mensagens novas após o registro, não lê o histórico, e mensagens de outros bots são ignoradas.
- `/revenda` informa o estado do modo; a estimativa financeira permanece desativada no bot até haver amostra de produtos equivalentes e custos configurados.

O monitor da watchlist roda a cada `POLL_INTERVAL_SECONDS` (mínimo 300, padrão 900). O Mercado Livre fica desligado por padrão; só habilite `ENABLE_MERCADO_LIVRE=true` após obter autorização e resolver o HTTP 403. Com a configuração padrão, não há marketplace ativo para produzir alertas. Alertas automáticos começam quando o bot está online e exigem uma conversa iniciada pelo usuário. Comandos e dados pessoais são restritos aos IDs autorizados. Para adicionar usuários ou alterar a fonte, atualize `.env` e reinicie.

## Pontuação e limites

O Hunter Score (0–100) é uma heurística explicável. Sem referência confiável, não inventa “preço de mercado”; sem reputação, não presume boa reputação. A pontuação considera diferença frente ao limite/referência ou observações locais, sinais de condição e risco. Ela não detecta falsificação por imagem nem prova legitimidade. Leia os motivos, abra o anúncio e mantenha pagamento e conversa nos mecanismos seguros do marketplace.

O filtro de encaminhamentos é baseado em preço máximo e palavra-chave no texto. Ele não confirma se o preço/link/foto são verdadeiros e não mede popularidade ou número de vendas. “Mais vendidos” só pode ser filtrado quando a fonte fornecer um dado de vendas verificável. Mensagens sem preço explícito `R$` precisam de revisão manual.

O histórico local começa vazio e cresce com cada observação. A referência do preço máximo configurado é um teto do usuário, não um valor de mercado. A detecção de redução significativa é de 5% em relação ao preço anteriormente observado. Dados repetidos por consulta podem refletir listagens e condições diferentes; compare modelo, capacidade, estado e frete antes de decidir.

## Execução após reiniciar o Windows

Use o Agendador de Tarefas: **Criar Tarefa Básica** → ao fazer logon → iniciar programa. Programa: `D:\HardwareHunterBR\.venv\Scripts\python.exe`; argumentos: `main.py`; iniciar em: `D:\HardwareHunterBR`. Deixe **Executar somente quando o usuário estiver conectado** se preferir acompanhar o console. Evite criar tarefas duplicadas.

## Manutenção e erros comuns

- `TELEGRAM_BOT_TOKEN ausente`: preencha `.env` e confirme que o arquivo está na raiz.
- `AUTHORIZED_USER_IDS ausente`: informe o ID numérico. Um bot privado sem IDs autorizados encerra para evitar acesso aberto.
- `Conflict: terminated by other getUpdates request`: encerre outra instância do mesmo bot.
- Erro de conexão/API: tente depois; confira internet e disponibilidade do Mercado Livre. O bot não tenta contornar bloqueios.
- Erro de dependência: ative `.venv` e rode `pip install -r requirements.txt`.
- Backup: pare o bot e copie `data\hardware_hunter.sqlite3`. Logs são enviados ao console; tokens não são registrados.

## Desenvolvimento

```powershell
python -m unittest discover -s tests -v
```

Os testes automatizados cobrem deduplicação e decisões básicas do pipeline. A integração de ponta a ponta exige autenticação MTProto autorizada e não é executada pela suíte para evitar contato com grupos reais.

Pastas: `hardware_hunter/` contém configuração, domínio, banco, bot, scheduler e analisadores; `marketplaces/` contém um adaptador independente por serviço; `tests/` contém dados sintéticos. `main.py` configura e inicia polling. Migrações futuras devem incrementar `SCHEMA_VERSION` e adicionar migração transacional antes de alterar o schema.

## Funcionalidades futuras/limitações

Comparador de verdade depende de identificação exata de SKU e integração em cada marketplace; agora a busca manual não agrega resultados de fontes desativadas. Detecção visual, compatibilidade de kits e revenda não são afirmadas sem dados apropriados. Resumo diário agendado, preferências de configuração por Telegram e comandos interativos de alteração de score/preço podem ser adicionados; os campos centrais de watchlist já ficam no banco, e o preço máximo pode ser definido em `/adicionar`.
