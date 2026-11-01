# Exemplos de atendimento em português

Base sintética criada para o ChamadoFlow. Não contém mensagens recebidas de clientes, registros de empresas ou dados pessoais reais.

- `train.json`: 96 exemplos, 16 para cada um dos seis assuntos.
- `test.json`: 44 exemplos; 6 por assunto e 8 perguntas fora do escopo, com rótulo esperado `triagem`.
- `create_dataset.py`, na raiz, reproduz os dois arquivos a partir dos textos definidos no projeto.

Os conjuntos foram escritos separadamente por finalidade. O treino não lê o teste. A avaliação verifica repetição de texto após normalização de caixa e acentos; não há sobreposição exata. Existem vocabulário e cenários semelhantes, próprios dos mesmos assuntos de atendimento.

O conjunto de teste é pequeno, sintético e relacionado ao desenvolvimento. É adequado para reproduzir a demonstração, investigar erros e comparar o encaminhamento com uma classe majoritária. Não sustenta conclusões de desempenho em uma operação real.

Para avaliar um novo domínio, são necessários exemplos representativos, rotulagem consistente e um conjunto externo separado do desenvolvimento e do ajuste dos limiares. A prioridade e os rascunhos são regras próprias e não são avaliados pelas métricas de classificação.
