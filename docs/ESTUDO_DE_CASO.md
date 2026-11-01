# ChamadoFlow — do relato à próxima ação

Uma fila de atendimento mistura problemas de entrega, acesso, pagamento e funcionamento. Quando o assunto não está claro, o relato precisa de triagem antes de chegar à equipe adequada. O ChamadoFlow reúne essa organização em um quadro operacional com histórico e sugestões locais.

## Experiência do produto

A tela principal apresenta chamados nas colunas Novos, Em atendimento e Resolvidos. O destaque de prazo ajuda a identificar o que merece atenção; filtros por equipe e prioridade organizam o recorte. Abrir um cartão leva ao relato, às ações de atendimento, ao histórico e ao rascunho de resposta.

O cadastro pede somente assunto, descrição e canal declarado. O modelo sugere uma categoria e a respectiva equipe. Quando os limiares não são atendidos, o sistema usa Triagem manual. O operador pode corrigir o assunto e a prioridade, registrar uma nota e avançar a situação.

## Decisões de implementação

**Classificação local.** O pipeline combina vetorização TF-IDF de palavras e caracteres com regressão logística. O modelo é treinado a partir de um JSON pequeno e fica em memória. A inferência não depende de serviços externos ou de artefatos executáveis serializados.

**Abstenção explícita.** Um candidato só vira sugestão de encaminhamento quando atende simultaneamente aos limites de pontuação, margem entre classes e similaridade com o treino. Os sinais e a justificativa ficam disponíveis no chamado. Eles não representam probabilidades calibradas nem uma garantia de acerto.

**Prioridade separada.** Expressões críticas, sugestões de melhoria e prioridade normal são tratadas por regras explícitas. A categoria não determina automaticamente a urgência. O operador pode corrigir ambas, e a sugestão inicial permanece registrada.

**Prazos reproduzíveis.** Datas são armazenadas com fuso UTC e exibidas em America/Sao_Paulo. Os limites demonstrativos são quatro, 24 ou 72 horas corridas. Mudanças de prioridade usam a criação como referência e não reiniciam o relógio. Chamados resolvidos são avaliados no instante de resolução.

**Persistência e concorrência.** Cada operação usa uma conexão SQLite com fechamento explícito e transação. Alterações bloqueiam a escrita durante a conferência da versão. Se outro atendimento já mudou o registro, a operação é recusada com conflito, preservando o estado mais recente. Os eventos registram criação e alterações com os estados anterior e posterior.

**Rascunhos controlados.** Cada categoria tem um modelo de texto local. Os modelos evitam confirmar entrega, estorno, cancelamento ou garantia sem análise. O produto exibe o texto para o operador copiar e adaptar; não envia mensagens a clientes.

**Ambientes separados.** A demonstração usa uma base com doze relatos fictícios. Meus chamados usa outro arquivo, inicialmente vazio. Isso permite explorar o fluxo e manter cadastros próprios separados dos exemplos.

## Evidências

A avaliação usa 96 textos sintéticos no treino e 44 na verificação. O F1 macro de encaminhamento é 0,804, comparado a 0,034 da classe majoritária. O acerto de encaminhamento é 79,5%. O modelo encaminhou 17 casos para triagem, incluindo os oito exemplos fora do escopo e nove de assuntos conhecidos. Os 27 encaminhamentos automáticos foram corretos nesse conjunto.

As métricas completas, a matriz de confusão e os resultados individuais ficam em `reports/evaluation.json`. O relatório explica que a base é pequena e sintética e que o conjunto de verificação está relacionado ao desenvolvimento. Não há medição de economia de horas, produtividade de equipe ou satisfação de clientes reais.

Os 37 testes verificam as regras de atendimento, prazos, histórico, correções, concorrência, API e navegação. A demonstração usa um modelo executado localmente; não há avaliação de LLM externo.

## Organização do código

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Quadro, cadastro, operação e apresentação da avaliação |
| `chamadoflow/triage.py` | Classificador, regras de prioridade e rascunhos |
| `chamadoflow/store.py` | Validação, SQLite, histórico e situação dos prazos |
| `chamadoflow/demo.py` | Chamados fictícios de demonstração |
| `chamadoflow/api.py` | Integração HTTP local |
| `chamadoflow/evaluation.py` | Avaliação e relatório reproduzível |

## Referências técnicas

- [scikit-learn: Pipeline](https://scikit-learn.org/stable/modules/generated/sklearn.pipeline.Pipeline.html)
- [scikit-learn: classification_report](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.classification_report.html)
- [Streamlit: estado por sessão e callbacks](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
