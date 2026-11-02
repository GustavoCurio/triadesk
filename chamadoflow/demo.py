"""Chamados fictícios relativos ao instante de criação da demonstração."""
from datetime import timedelta

from .store import ChangeTicket, NewTicket, utcnow


def seed_demo(store, now=None):
    """Popula uma base vazia com doze chamados fictícios e suas transições.

    Args:
        store: Store da demonstração; base com qualquer chamado é preservada.
        now: Referência com fuso para os deslocamentos de tempo, ou utcnow.

    Cada coluna recebe quatro exemplos. Datas relativas permitem mostrar
    prazos vencidos e próximos do vencimento na primeira execução. O cache
    da interface coordena a inicialização; esta rotina não garante um seed
    atômico entre processos concorrentes nem repõe uma carga parcial.
    """
    if store.list():
        return
    now = now or utcnow()
    samples = [
        ("Entrega sem atualização", "Minha encomenda está parada na transportadora e o rastreio não muda há dias.", "Novo", 28),
        ("Cobrança duplicada", "O valor da compra aparece duas vezes na fatura do meu cartão de crédito.", "Novo", 2),
        ("Recuperação de conta", "Esqueci a senha e o link para recuperar o acesso ao perfil não chegou.", "Novo", 1),
        ("Dúvida de outro assunto", "Gostaria de uma receita de bolo de cenoura para preparar no fim de semana.", "Novo", 0.5),
        ("Aplicação indisponível", "O sistema fora do ar está afetando todos os usuários e a página não carrega.", "Em atendimento", 6),
        ("Produto danificado", "O aparelho veio com a tampa quebrada e faltam peças dentro da embalagem.", "Em atendimento", 8),
        ("Pedido de devolução", "Quero devolver a compra e saber como receber a etiqueta de logística reversa.", "Em atendimento", 10),
        ("Pagamento pendente", "Meu boleto foi pago ontem e o pedido continua aguardando confirmação do pagamento.", "Em atendimento", 22),
        ("Rastreio localizado", "Não consigo acompanhar o envio da encomenda pelo código de rastreamento.", "Resolvido", 20),
        ("Atualização de cadastro", "Preciso alterar o e-mail e o telefone cadastrados no meu perfil da conta.", "Resolvido", 30),
        ("Erro na exportação", "A aplicação retorna erro de conexão ao exportar o relatório em todas as telas.", "Resolvido", 12),
        ("Cancelamento acompanhado", "Preciso cancelar minha assinatura e interromper a renovação automática.", "Resolvido", 40),
    ]
    for index, (title, description, status, hours) in enumerate(samples):
        created = now - timedelta(hours=hours)
        ticket = store.create(NewTicket(title=title, description=description, channel=["Portal", "E-mail", "WhatsApp"][index % 3]), created)
        if status != "Novo":
            ticket = store.update(ticket["id"], ChangeTicket(version=ticket["version"], status="Em atendimento", category=ticket["category"], priority=ticket["priority"], note="Atendimento demonstrativo iniciado."), created + timedelta(minutes=10))
        if status == "Resolvido":
            store.update(ticket["id"], ChangeTicket(version=ticket["version"], status="Resolvido", category=ticket["category"], priority=ticket["priority"], note="Caso fictício encerrado para demonstrar o fluxo."), created + timedelta(hours=2))
