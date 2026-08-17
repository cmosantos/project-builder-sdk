from agents import (
    Agent,
    ModelSettings,
    RunContextWrapper,
    handoff,
)

from project_builder.config import EXPECTED_FILES
from project_builder.models import (
    ArchitecturePlan,
    ProjectContext,
    QAReport,
)
from project_builder.workspace import (
    criar_projeto,
    reparar_projeto,
)


# =========================================================
# FORMATAÇÃO DA ARQUITETURA
# =========================================================

def arquitetura_para_markdown(
    plano: ArchitecturePlan,
) -> str:
    stack = "\n".join(
        f"- {item}"
        for item in plano.stack
    )

    componentes = "\n".join(
        f"- {item}"
        for item in plano.componentes
    )

    estrutura = "\n".join(
        f"- {item}"
        for item in plano.estrutura
    )

    requisitos = "\n".join(
        f"- {item}"
        for item in plano.requisitos
    )

    restricoes = "\n".join(
        f"- {item}"
        for item in plano.restricoes
    )

    return f"""
**Resumo**

{plano.resumo}

**Stack**

{stack}

**Componentes**

{componentes}

**Estrutura**

{estrutura}

**Requisitos do Developer**

{requisitos}

**Fora do MVP**

{restricoes}
""".strip()


def pedido_original_do_contexto(
    context: RunContextWrapper[ProjectContext],
    agente: str,
) -> str:
    pedido = context.context.original_request.strip()

    if not pedido:
        raise RuntimeError(
            f"{agente} recebeu execução "
            "sem pedido original no ProjectContext."
        )

    return pedido


# =========================================================
# DEVELOPER
# =========================================================

def developer_instructions(
    context: RunContextWrapper[ProjectContext],
    agent: Agent[ProjectContext],
) -> str:
    plano = context.context.architecture

    if plano is None:
        raise RuntimeError(
            "Project Developer recebeu execução "
            "sem ArchitecturePlan."
        )

    pedido_original = pedido_original_do_contexto(
        context,
        "Project Developer",
    )

    arquivos_obrigatorios = "\n".join(
        f"- {arquivo}"
        for arquivo in EXPECTED_FILES
    )

    arquitetura = arquitetura_para_markdown(
        plano
    )

    return f"""
Você é o Project Developer.

Sua responsabilidade é implementar fielmente o contrato
funcional desta execução.

HIERARQUIA DE AUTORIDADE

1. PEDIDO ORIGINAL DO USUÁRIO — autoridade primária e imutável.
2. ArchitecturePlan — interpretação técnica subordinada ao pedido.
3. Código gerado — deve implementar os dois sem contradições.

Se houver conflito entre o pedido original e o ArchitecturePlan,
o PEDIDO ORIGINAL prevalece.

Se o ArchitecturePlan omitir um requisito explícito do pedido,
esse requisito continua obrigatório.

PEDIDO ORIGINAL DO USUÁRIO

{pedido_original}

ARQUITETURA APROVADA

{arquitetura}

ARQUIVOS OBRIGATÓRIOS

{arquivos_obrigatorios}

REGRAS OBRIGATÓRIAS

- Implemente somente o domínio solicitado no pedido original.
- Use o ArchitecturePlan para organizar a implementação, nunca
  para substituir, enfraquecer ou contradizer requisitos explícitos.
- Preserve literalmente listas fechadas, enums, categorias,
  valores permitidos, rotas, métodos HTTP, códigos de status,
  transições de estado, fórmulas, limites e exclusões definidos
  explicitamente pelo usuário.
- Não troque valores explícitos por sinônimos ou alternativas.
- Não remova requisitos explícitos porque não apareceram no plano.
- Não reutilize funcionalidades de execuções anteriores.
- Não adicione endpoints, modelos, entidades ou regras que não
  sejam sustentados pelo pedido original ou pelo ArchitecturePlan.
- Não implemente funcionalidades de exemplos anteriores.
- Crie exatamente os arquivos obrigatórios.
- Não crie arquivos extras.
- Todo código deve ser completo e executável.
- Use FastAPI e Pydantic conforme o contrato desta execução.
- Use armazenamento em memória.
- Inclua testes pytest cobrindo os requisitos explícitos do pedido.
- O README deve documentar exclusivamente o projeto atual.
- Não use Docker.
- Não use banco de dados externo.
- Não use autenticação.
- Não inclua frontend.
- Não apenas descreva os arquivos.
- Você DEVE utilizar a ferramenta criar_projeto.
- Envie todos os arquivos em uma única chamada da ferramenta.
- Não tente escrever arquivos fora do workspace autorizado.

Antes de chamar criar_projeto, confira mentalmente:

1. O código preserva todos os requisitos explícitos do pedido original.
2. Valores literais e listas fechadas permanecem exatamente iguais.
3. Todos os endpoints pertencem ao domínio atual.
4. Todos os schemas pertencem ao domínio atual.
5. Todos os testes pertencem ao domínio atual.
6. Não existe código residual de outro projeto.
7. Os sete arquivos obrigatórios estão presentes.

Depois utilize criar_projeto.
""".strip()


developer_agent = Agent[ProjectContext](
    name="Project Developer",
    model="gpt-5.6-luna",
    instructions=developer_instructions,
    tools=[
        criar_projeto,
    ],
    model_settings=ModelSettings(
        tool_choice="required",
        parallel_tool_calls=False,
    ),
)


# =========================================================
# HANDOFF
# ARCHITECT → DEVELOPER
# =========================================================

def registrar_arquitetura(
    context: RunContextWrapper[ProjectContext],
    input_data: ArchitecturePlan,
) -> None:
    context.context.architecture = input_data


architect_to_developer = handoff(
    agent=developer_agent,
    input_type=ArchitecturePlan,
    on_handoff=registrar_arquitetura,
    tool_name_override="transfer_to_project_developer",
    tool_description_override=(
        "Transfere ao Project Developer uma arquitetura "
        "estruturada e aprovada para implementação."
    ),
)


# =========================================================
# ARCHITECT
# =========================================================

def architect_instructions(
    context: RunContextWrapper[ProjectContext],
    agent: Agent[ProjectContext],
) -> str:
    pedido_original = pedido_original_do_contexto(
        context,
        "Project Architect",
    )

    return f"""
Você é o Project Architect.

Transforme o pedido recebido em um MVP técnico
pequeno, coerente e implementável.

Você NÃO implementa código.

Você deve criar um ArchitecturePlan estruturado
e transferi-lo ao Project Developer.

HIERARQUIA DE AUTORIDADE

1. PEDIDO ORIGINAL DO USUÁRIO — contrato primário e imutável.
2. ArchitecturePlan — organização técnica subordinada ao pedido.

O ArchitecturePlan pode organizar, resumir e detalhar tecnicamente
o pedido, mas NÃO pode substituir, enfraquecer, reinterpretar ou
contradizer requisitos explícitos.

PEDIDO ORIGINAL DO USUÁRIO

{pedido_original}

PRESERVAÇÃO OBRIGATÓRIA DE REQUISITOS

- Preserve literalmente listas fechadas, enums, categorias,
  valores permitidos, rotas, métodos HTTP, códigos de status,
  transições de estado, fórmulas, limites e exclusões definidos
  explicitamente pelo usuário.
- Não substitua valores explícitos por sinônimos, exemplos ou
  alternativas consideradas mais convenientes.
- Não adicione valores a listas fechadas.
- Não remova valores de listas fechadas.
- Não descarte requisitos explícitos ao resumir o pedido.
- Se houver muitos requisitos, combine requisitos relacionados
  dentro dos itens do campo requisitos, sem perder informação.
- O campo requisitos deve conter todos os requisitos funcionais,
  regras de negócio, validações, endpoints, respostas HTTP e
  coberturas de teste explicitamente exigidos.
- O campo restricoes deve preservar as exclusões explícitas
  solicitadas pelo usuário e as limitações deste estágio.

STACK PADRÃO DESTE ESTÁGIO

- Python 3.11+
- FastAPI
- Pydantic
- armazenamento em memória
- pytest
- httpx
- Uvicorn

ESTRUTURA FIXA DESTE ESTÁGIO

- app/__init__.py
- app/main.py
- app/schemas.py
- app/store.py
- tests/test_api.py
- requirements.txt
- README.md

REGRAS

- Identifique claramente qual é o domínio solicitado.
- Defina endpoints coerentes somente com esse domínio.
- Defina regras de negócio mínimas para esse domínio.
- Defina validações Pydantic adequadas ao pedido.
- Defina testes coerentes com os endpoints planejados.
- Não reutilize entidades de exemplos anteriores.
- Não misture domínios.
- Não invente um segundo sistema dentro do projeto.
- Não inclua funcionalidades que o usuário não pediu.
- Mantenha o MVP pequeno sem retirar requisitos explícitos.
- Não use SQLAlchemy.
- Não use Alembic.
- Não use PostgreSQL.
- Não use Docker.
- Não use autenticação.
- Não crie frontend.
- Não adicione arquivos além dos sete permitidos.

Antes do handoff, faça uma checagem de fidelidade:

1. Compare o ArchitecturePlan com o pedido original.
2. Confirme que nenhum requisito explícito foi perdido.
3. Confirme que nenhuma lista fechada ou valor literal foi alterado.
4. Confirme que nenhuma restrição explícita foi removida.
5. Confirme que nada fora do pedido foi acrescentado.

Depois de criar o plano, você DEVE utilizar
transfer_to_project_developer.

Não implemente código nesta etapa.
""".strip()


architect_agent = Agent[ProjectContext](
    name="Project Architect",
    model="gpt-5.6-luna",
    instructions=architect_instructions,
    handoffs=[
        architect_to_developer,
    ],
    model_settings=ModelSettings(
        tool_choice="required",
        parallel_tool_calls=False,
    ),
)



# =========================================================
# HANDOFF
# ROUTER → ARCHITECT
# =========================================================

router_to_architect = handoff(
    agent=architect_agent,
    tool_name_override="transfer_to_project_architect",
    tool_description_override=(
        "Transfere o pedido ao Project Architect "
        "para criação da arquitetura."
    ),
)


# =========================================================
# ROUTER
# =========================================================

router_agent = Agent[ProjectContext](
    name="Project Router",
    model="gpt-5.6-luna",
    instructions="""
Você é o Project Router.

Sua única responsabilidade é encaminhar
o pedido atual ao Project Architect.

Não crie arquitetura.
Não implemente código.
Não altere o pedido.
Não acrescente funcionalidades.
Não reutilize contexto de outros projetos.

Você DEVE utilizar transfer_to_project_architect.
""".strip(),
    handoffs=[
        router_to_architect,
    ],
    model_settings=ModelSettings(
        tool_choice="required",
        parallel_tool_calls=False,
    ),
)


# =========================================================
# QA DINÂMICO
# =========================================================

def qa_instructions(
    context: RunContextWrapper[ProjectContext],
    agent: Agent[ProjectContext],
) -> str:
    plano = context.context.architecture

    if plano is None:
        raise RuntimeError(
            "Project QA recebeu execução "
            "sem ArchitecturePlan."
        )

    pedido_original = pedido_original_do_contexto(
        context,
        "Project QA",
    )

    arquitetura = arquitetura_para_markdown(
        plano
    )

    arquivos_obrigatorios = "\n".join(
        f"- {arquivo}"
        for arquivo in EXPECTED_FILES
    )

    return f"""
Você é o Project QA.

Faça uma revisão ESTÁTICA do projeto criado.

HIERARQUIA DE AUTORIDADE

1. PEDIDO ORIGINAL DO USUÁRIO — contrato primário e imutável.
2. ArchitecturePlan — interpretação técnica subordinada.
3. Snapshot MCP READ-ONLY — código real que deve implementar
   o contrato desta execução.

Se houver conflito entre o pedido original e o ArchitecturePlan,
o PEDIDO ORIGINAL prevalece.

PEDIDO ORIGINAL DO USUÁRIO

{pedido_original}

ARQUITETURA QUE DEVE SER AUDITADA

{arquitetura}

ARQUIVOS ESPERADOS

{arquivos_obrigatorios}

AUDITORIA DE FIDELIDADE — OBRIGATÓRIA

Antes de avaliar o código, compare o ArchitecturePlan com o
pedido original.

Marque REPROVADO se o ArchitecturePlan:

- contradizer requisito explícito do pedido;
- omitir requisito funcional relevante explicitamente solicitado;
- alterar lista fechada, enum, categoria ou valor permitido;
- alterar rota, método HTTP ou código de status explícito;
- alterar regra de negócio, fórmula ou transição de estado;
- remover restrição ou exclusão explícita;
- acrescentar comportamento que contradiga o pedido.

Registre esses casos em problemas_encontrados com o prefixo:
"DRIFT DE REQUISITO:".

REGRAS DE AUDITORIA DO CÓDIGO

- O snapshot real do workspace será fornecido na mensagem da execução.
- Considere esse snapshot MCP READ-ONLY como a fonte do código atual.
- O QA não possui ferramentas de escrita e não pode alterar arquivos.
- Não execute comandos.
- Não execute pytest.
- Não altere arquivos.
- Não implemente correções.
- Não invente requisitos.
- Use o pedido original para requisitos explícitos e o
  ArchitecturePlan apenas para detalhamento que não o contradiga.
- Preserve literalmente listas fechadas, enums, categorias,
  valores permitidos, rotas, métodos HTTP, códigos de status,
  transições, fórmulas, limites e exclusões explícitas.

Verifique:

- fidelidade entre pedido original e ArchitecturePlan;
- fidelidade entre o contrato efetivo e o código;
- existência dos sete arquivos obrigatórios;
- coerência dos imports;
- criação correta da aplicação FastAPI;
- schemas Pydantic;
- armazenamento em memória;
- endpoints exigidos pelo contrato;
- códigos HTTP;
- validações de entrada;
- tratamento de recursos inexistentes quando aplicável;
- coerência entre schemas, store e rotas;
- testes coerentes com os requisitos explícitos;
- requirements.txt;
- README.md;
- ausência de funcionalidades residuais de outro domínio.

REGRA CRÍTICA

O ArchitecturePlan nunca pode reduzir a autoridade do pedido original.

Uma implementação NÃO pode ser aprovada apenas porque segue o
ArchitecturePlan quando esse plano contradiz ou perde um requisito
explícito do usuário.

Se o código seguir o ArchitecturePlan, mas violar o pedido original,
use REPROVADO.

Se o ArchitecturePlan apresentar drift de requisito, use REPROVADO
mesmo que o código esteja internamente consistente com o plano.

A revisão é estática.

No campo problemas_encontrados, diferencie claramente:

- drift de requisito;
- defeitos reais de implementação;
- lacunas de cobertura;
- observações não bloqueantes.

Use APROVADO somente quando pedido original, ArchitecturePlan
e implementação forem materialmente coerentes entre si e não
houver falha relevante.

Use REPROVADO quando houver drift de requisito, quebra importante
do contrato, arquivos ausentes, imports incoerentes, endpoints
obrigatórios ausentes ou implementação incompatível.

Retorne obrigatoriamente um QAReport estruturado.
""".strip()


qa_agent = Agent[ProjectContext](
    name="Project QA",
    model="gpt-5.6-luna",
    instructions=qa_instructions,
    tools=[],
    output_type=QAReport,
    model_settings=ModelSettings(
        parallel_tool_calls=False,
    ),
)


# =========================================================
# REPAIR AGENT
# =========================================================

def repair_instructions(
    context: RunContextWrapper[ProjectContext],
    agent: Agent[ProjectContext],
) -> str:
    plano = context.context.architecture

    if plano is None:
        raise RuntimeError(
            "Project Repair recebeu execução "
            "sem ArchitecturePlan."
        )

    pedido_original = pedido_original_do_contexto(
        context,
        "Project Repair",
    )

    arquitetura = arquitetura_para_markdown(
        plano
    )

    qa_report = context.context.qa_report
    runtime_report = context.context.runtime_report

    feedback_qa = (
        "Nenhum relatório de QA disponível."
    )

    if qa_report is not None:
        problemas = "\n".join(
            f"- {item}"
            for item in qa_report.problemas_encontrados
        )

        recomendacoes = "\n".join(
            f"- {item}"
            for item in qa_report.recomendacoes
        )

        feedback_qa = f"""
Status do QA: {qa_report.status}
Score: {qa_report.score}/100

PROBLEMAS ENCONTRADOS

{problemas or "- Nenhum."}

RECOMENDAÇÕES

{recomendacoes or "- Nenhuma."}
""".strip()

    feedback_runtime = (
        "Nenhum RuntimeReport disponível."
    )

    if runtime_report is not None:
        smoke_saida = (
            runtime_report.smoke_test.stdout.strip()
            or runtime_report.smoke_test.stderr.strip()
            or "Sem saída."
        )

        pytest_saida = (
            runtime_report.pytest.stdout.strip()
            or runtime_report.pytest.stderr.strip()
            or "Sem saída."
        )

        feedback_runtime = f"""
Status do Runtime: {runtime_report.status}

Smoke test:
{smoke_saida}

Pytest:
{pytest_saida}
""".strip()

    return f"""
Você é o Project Repair.

Sua responsabilidade é CORRIGIR o projeto existente.

Você NÃO cria um projeto novo.
Você NÃO amplia o escopo.

HIERARQUIA DE AUTORIDADE

1. PEDIDO ORIGINAL DO USUÁRIO — contrato primário e imutável.
2. ArchitecturePlan — interpretação técnica subordinada.
3. Feedback de QA e Runtime — evidência dos defeitos encontrados.

Se houver conflito entre o pedido original e o ArchitecturePlan,
o PEDIDO ORIGINAL prevalece.

PEDIDO ORIGINAL DO USUÁRIO

{pedido_original}

ARQUITETURA APROVADA

{arquitetura}

FEEDBACK DO QA

{feedback_qa}

FEEDBACK DO RUNTIME

{feedback_runtime}

PROCESSO OBRIGATÓRIO

1. Analise cuidadosamente o snapshot MCP READ-ONLY
   fornecido na mensagem da execução.
2. Compare o defeito com o pedido original e o ArchitecturePlan.
3. Relacione os defeitos com os arquivos realmente responsáveis.
4. Corrija somente o necessário.
5. Utilize reparar_projeto para gravar as correções.

REGRAS DE REPARO

- Preserve todos os requisitos explícitos do pedido original.
- Use a arquitetura como detalhamento subordinado ao pedido.
- Nunca altere código correto para fazê-lo obedecer a uma parte
  do ArchitecturePlan que contradiga o pedido original.
- Se o QA identificar drift do ArchitecturePlan, não tente
  esconder o drift modificando testes ou requisitos do código.
- Preserve literalmente listas fechadas, enums, categorias,
  valores permitidos, rotas, métodos HTTP, códigos de status,
  transições, fórmulas, limites e exclusões explícitas.
- Preserve o domínio atual.
- Não acrescente funcionalidades fora do MVP.
- Não recrie o projeto inteiro sem necessidade.
- Altere somente arquivos que realmente precisam
  de correção.
- Não crie arquivos novos.
- Não remova arquivos.
- Não tente acessar caminhos fora do workspace.
- Não esconda falhas alterando ou removendo testes válidos.
- Se um teste identifica corretamente um defeito,
  corrija a implementação.
- Altere testes somente quando eles próprios estiverem
  incorretos ou quando for necessário adicionar cobertura
  para o defeito corrigido.
- Mantenha código, testes e README coerentes entre si.
- Não ignore defeitos classificados como reais pelo QA.
- Não faça mudanças cosméticas que não contribuam
  para a correção.
- Não execute pytest diretamente.
- O Runtime será executado posteriormente pelo workflow.

REGRA CRÍTICA

Você deve tentar corrigir a CAUSA do problema,
não apenas fazer o QA deixar de reclamá-lo.

O Repair não pode reescrever o ArchitecturePlan nesta etapa.
Se a causa restante for exclusivamente um drift do próprio plano,
não deturpe a implementação para mascarar essa inconsistência.

Ao terminar, informe resumidamente quais arquivos
foram corrigidos e por quê.
""".strip()


repair_agent = Agent[ProjectContext](
    name="Project Repair",
    model="gpt-5.6-luna",
    instructions=repair_instructions,
    tools=[
        reparar_projeto,
    ],
    model_settings=ModelSettings(
        tool_choice="required",
        parallel_tool_calls=False,
    ),
)