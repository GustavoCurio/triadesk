"""Reproduz os arquivos sintéticos de treino e verificação do TriaDesk.

Os textos são definidos explicitamente neste script. Ao executar ou importar
o arquivo, data/train.json e data/test.json são sobrescritos em UTF-8.
Não utiliza relatos de clientes nem realiza coleta ou geração externa.
"""
from pathlib import Path
import json
root = Path(__file__).resolve().parent / "data"
root.mkdir(parents=True,exist_ok=True)
train={
"entrega": """Meu pedido está atrasado e ainda não chegou à minha casa|Preciso do código de rastreamento da encomenda|O rastreio diz entregue mas não recebi o pacote|Quero consultar a previsão de entrega do pedido|A transportadora não localizou meu endereço|Meu pacote está parado no centro de distribuição|Como acompanhar o envio da minha compra|O entregador veio mas eu não estava em casa|Minha encomenda foi enviada para outra cidade|Gostaria de corrigir o endereço antes da entrega|Não consigo rastrear o pedido na transportadora|Faltou informar o complemento do endereço de entrega|O prazo para receber o pacote já terminou|A entrega está com status de destinatário ausente|O pedido não saiu para transporte até agora|Onde está a encomenda que comprei na semana passada""",
"pagamento": """Meu cartão foi cobrado duas vezes pela mesma compra|O boleto foi pago mas ainda consta pendente|Quero a segunda via do boleto de pagamento|Meu pix foi feito e o pagamento não foi reconhecido|A cobrança no cartão apresenta um valor diferente|Não consigo pagar usando cartão de crédito|Como alterar a forma de pagamento da compra|As parcelas do cartão estão com valores incorretos|Recebi uma cobrança que não reconheço na fatura|Preciso confirmar se o pagamento foi aprovado|O checkout recusou meu cartão de débito|Estou com dúvida sobre o vencimento do boleto|A transação aparece duplicada no extrato|O valor cobrado foi maior que o total da compra|Existe alguma opção para parcelar o pagamento|O comprovante de pix foi gerado mas o valor não baixou""",
"conta": """Esqueci minha senha e não consigo entrar na conta|O link de recuperação de senha expirou|Preciso trocar o e-mail cadastrado no meu perfil|Não recebo o código de verificação para login|Minha conta foi bloqueada depois de tentar acessar|Como atualizar meu telefone no cadastro|Quero recuperar o acesso ao meu perfil|O sistema informa usuário ou senha inválidos|Meu cadastro usa um e-mail antigo que não tenho mais|Gostaria de ativar a verificação em duas etapas|Preciso alterar os dados do meu cadastro|O código de autenticação está sendo rejeitado|Fiz um cadastro e não chegou o e-mail de ativação|Perdi o acesso ao telefone usado no login|Suspeito que minha conta foi acessada por outra pessoa|Minha conta invadida teve a senha alterada""",
"produto": """O produto chegou quebrado dentro da embalagem|O equipamento não liga mesmo conectado à tomada|Recebi um item com peças faltando|O tamanho do produto é diferente do anunciado|A cor do produto recebido não corresponde à foto|O aparelho apresenta defeito depois de poucos dias|Gostaria de saber como acionar a garantia do produto|A embalagem veio sem o acessório que acompanha o item|A mercadoria apresenta rachaduras e riscos|O produto está com funcionamento irregular|Recebi um modelo diferente daquele que comprei|O material do item veio rasgado|A qualidade do produto ficou abaixo da descrição|Preciso do manual de uso do equipamento|Um dos componentes do kit veio danificado|O aparelho faz ruído estranho durante o uso""",
"cancelamento": """Quero cancelar meu pedido antes do envio|Como faço para devolver minha compra|Desisti da compra e gostaria de solicitar reembolso|Quero saber o prazo de devolução dos produtos|Preciso cancelar a assinatura que contratei|Onde encontro a etiqueta de logística reversa|Gostaria de acompanhar a solicitação de estorno|Já devolvi o item e aguardo o reembolso|Solicito o cancelamento da compra feita ontem|Quero exercer a desistência e devolver o pedido|Meu pedido de devolução não foi respondido|Como enviar o produto de volta para a loja|Preciso interromper a renovação da assinatura|O estorno da compra cancelada ainda não apareceu|Gostaria de trocar a compra por devolução do valor|Cancelei o pedido e preciso acompanhar o processo""",
"tecnico": """O site apresenta erro 500 quando abro a página|O aplicativo fecha sozinho depois da atualização|O botão de salvar não responde ao clique|O sistema fora do ar impede o trabalho da equipe|A página fica em branco no navegador|A integração da API retorna erro de conexão|Não consigo anexar arquivos porque o upload falha|O aplicativo está muito lento em todas as telas|O relatório trava durante a exportação|A tela apresenta um erro inesperado ao carregar|O sistema indisponível está afetando todos os usuários|O serviço retorna timeout ao consultar a API|O formulário não salva as alterações realizadas|O navegador mostra uma mensagem de falha no servidor|O sistema duplica registros ao clicar no botão|Sugestão de melhoria futura na navegação do aplicativo"""
}
test={
"entrega":[
"Minha compra não chegou no dia prometido pela transportadora.",
"O rastreamento da encomenda está sem movimentação há uma semana.",
"Preciso incluir o número do apartamento no endereço de entrega.",
"O entregador registrou recebimento, porém ninguém recebeu o pacote.",
"Qual o prazo para o envio do meu pedido para minha cidade?",
"O transporte do pacote está atrasado, podem verificar o rastreio?"
],
"pagamento":[
"Paguei o boleto ontem e a compra continua aguardando pagamento.",
"Há duas cobranças iguais do meu cartão para uma única compra.",
"Quero parcelar o valor, quais formas de pagamento vocês aceitam?",
"Meu pix saiu da conta, mas a transação não foi confirmada.",
"A fatura trouxe um valor cobrado diferente do combinado.",
"O pagamento com cartão foi recusado no checkout novamente."
],
"conta":[
"A senha foi esquecida e preciso de outro link para recuperar meu acesso.",
"Troquei meu celular e não consigo receber o código de autenticação.",
"Como mudar o endereço de e-mail do meu cadastro?",
"Tento fazer login e aparece a mensagem de usuário inválido.",
"Meu perfil está bloqueado e quero recuperar a conta.",
"O e-mail para ativar meu cadastro ainda não foi recebido."
],
"produto":[
"A mercadoria recebida está rachada e faltam peças no kit.",
"O aparelho novo parou de funcionar e quero orientações da garantia.",
"Veio uma cor diferente no produto que recebi.",
"A embalagem estava fechada, mas o acessório não veio junto.",
"O equipamento não liga e apresenta um ruído estranho.",
"Gostaria do manual e das instruções de uso desse produto."
],
"cancelamento":[
"Desisti e desejo cancelar a compra que ainda não foi enviada.",
"Já postei a devolução e quero acompanhar meu reembolso.",
"Quero parar a renovação automática da minha assinatura.",
"Como solicitar a etiqueta para enviar a compra de volta?",
"O pedido foi cancelado, mas ainda estou esperando o estorno.",
"Qual o procedimento para devolver a mercadoria e receber o valor?"
],
"tecnico":[
"A aplicação fecha toda vez que tento exportar um relatório.",
"Recebo erro 500 e a página do site não carrega.",
"A API da integração está dando timeout nas consultas.",
"O botão de anexar não funciona e o upload fica travado.",
"O sistema está indisponível para todos os usuários da empresa.",
"A tela fica branca e o navegador informa falha de conexão com o servidor."
],
"triagem":[
"Qual é a receita de um bolo de cenoura?",
"Gostaria de uma previsão do tempo para amanhã.",
"Quero aprender a tocar violão e estudar música.",
"Quantas luas existem no planeta Júpiter?",
"Indique um roteiro de turismo para minhas férias.",
"Estou procurando dicas de jardinagem para plantar tomates.",
"Você consegue traduzir um poema em italiano?",
"Preciso de uma recomendação de filme de aventura."
]
}
train_rows=[{"text":t,"category":c} for c,texts in train.items() for t in texts.split("|")]
test_rows=[{"text":t,"category":c} for c,texts in test.items() for t in texts]
for name,rows in [("train.json",train_rows),("test.json",test_rows)]:
    (root/name).write_text(json.dumps(rows,ensure_ascii=False,indent=2),"utf-8")
print(len(train_rows),"treino;",len(test_rows),"teste")