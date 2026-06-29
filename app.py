from flask import Flask, render_template, request, redirect, session, jsonify, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from functools import wraps
from sqlalchemy import inspect, text


# ==========================
# APP CONFIG
# ==========================
app = Flask(__name__, instance_relative_config=True)
app.secret_key = os.environ.get("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("A variável SECRET_KEY não foi configurada.")

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

db_url = os.environ.get("DATABASE_URL")

if not db_url:
    db_url = "sqlite:///clinica.db"
else:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

print("SQLALCHEMY_DATABASE_URI:", app.config["SQLALCHEMY_DATABASE_URI"])

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ==========================
# PROTEÇÃO GLOBAL DE LOGIN
# ==========================
@app.before_request
def proteger_rotas():
    rotas_livres = [
        "login",
        "static",
        "verificar_usuario"
    ]

    if request.endpoint in rotas_livres:
        return

    if not session.get("logado"):
        return redirect("/login")


# ==========================
# MODELOS
# ==========================
class Profissional(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    especialidade = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(100))


class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    especialidade = db.Column(db.String(100), nullable=False)


class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"), nullable=True)
    paciente = db.relationship("Paciente", backref="agendamentos")

    profissional_id = db.Column(db.Integer, db.ForeignKey("profissional.id"))
    profissional = db.relationship("Profissional", backref="agendamentos")

    servico_id = db.Column(db.Integer, db.ForeignKey("servico.id"))
    servico = db.relationship("Servico", backref="agendamentos")

    cliente_nome = db.Column(db.String(100))
    cliente_telefone = db.Column(db.String(20))
    cliente_email = db.Column(db.String(120))
    cliente_cpf = db.Column(db.String(20))
    cliente_data_nascimento = db.Column(db.String(20))

    observacoes_paciente = db.Column(db.Text)
    observacoes_consulta = db.Column(db.Text)

    data = db.Column(db.String(20), nullable=False)
    horario = db.Column(db.String(20), nullable=False)

    valor = db.Column(db.Float, default=0)
    forma_pagamento = db.Column(db.String(50), default="Não informado")
    pagamento_realizado = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="Aguardando")


class Financeiro(db.Model):
    __tablename__ = "financeiro"

    id = db.Column(db.Integer, primary_key=True)

    descricao = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    categoria = db.Column(db.String(100))

    valor = db.Column(db.Float, nullable=False)

    data = db.Column(db.Date)
    data_vencimento = db.Column(db.Date)

    forma_pagamento = db.Column(db.String(50))
    status = db.Column(db.String(30), default="Recebido")

    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"), nullable=True)
    paciente = db.relationship("Paciente", backref="financeiros")

    profissional_id = db.Column(db.Integer, db.ForeignKey("profissional.id"), nullable=True)
    profissional = db.relationship("Profissional", backref="financeiros")

    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamento.id"), nullable=True)
    agendamento = db.relationship("Agendamento", backref="financeiros")

    observacoes = db.Column(db.Text)

    criado_em = db.Column(db.DateTime, default=db.func.now())


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(20), default="recepcao")


class RecuperacaoSenha(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="Pendente")
    nova_senha = db.Column(db.String(100))


class Paciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(100), nullable=False)
    data_nascimento = db.Column(db.String(20))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))

    cpf = db.Column(db.String(20))
    convenio = db.Column(db.String(100))
    plano = db.Column(db.String(100))
    observacoes = db.Column(db.Text)

    estado_civil = db.Column(db.String(50))
    cidade = db.Column(db.String(100))
    endereco = db.Column(db.String(200))
    idade = db.Column(db.Integer)
    profissao = db.Column(db.String(100))
    sexo = db.Column(db.String(20))


class Autorizacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"))
    paciente = db.relationship("Paciente", backref="autorizacoes")

    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamento.id"))

    data = db.Column(db.String(20))
    texto = db.Column(db.Text)

    assinatura = db.Column(db.Text)
    aceite = db.Column(db.Boolean, default=False)


def garantir_colunas_agendamento():
    """
    Garante que bancos antigos também tenham os novos campos da agenda.
    Isso evita erro no Render quando o banco já existia antes da alteração.
    """
    inspector = inspect(db.engine)
    colunas = [coluna["name"] for coluna in inspector.get_columns("agendamento")]
    dialecto = db.engine.dialect.name

    if "forma_pagamento" not in colunas:
        db.session.execute(text("ALTER TABLE agendamento ADD COLUMN forma_pagamento VARCHAR(50) DEFAULT 'Não informado'"))

    if "pagamento_realizado" not in colunas:
        if dialecto == "postgresql":
            db.session.execute(text("ALTER TABLE agendamento ADD COLUMN pagamento_realizado BOOLEAN DEFAULT FALSE"))
        else:
            db.session.execute(text("ALTER TABLE agendamento ADD COLUMN pagamento_realizado BOOLEAN DEFAULT 0"))

    db.session.commit()


with app.app_context():
    db.create_all()
    garantir_colunas_agendamento()

    # Cria serviços padrão caso a tabela esteja vazia.
    # Isso faz o campo "Serviço / Especialidade" aparecer na tela de agendamentos.
    if Servico.query.count() == 0:
        servicos_padrao = [
            Servico(nome="Consulta", especialidade="Clínico Geral"),
            Servico(nome="Retorno", especialidade="Clínico Geral"),
            Servico(nome="Avaliação", especialidade="Avaliação"),
            Servico(nome="Procedimento", especialidade="Procedimento"),
            Servico(nome="Exame", especialidade="Exame"),
        ]

        # Também cria serviços com base nas especialidades dos profissionais cadastrados.
        especialidades = db.session.query(Profissional.especialidade).distinct().all()
        nomes_existentes = {item.nome.lower().strip() for item in servicos_padrao}

        for (especialidade,) in especialidades:
            if especialidade and especialidade.lower().strip() not in nomes_existentes:
                servicos_padrao.append(
                    Servico(nome=especialidade, especialidade=especialidade)
                )

        db.session.add_all(servicos_padrao)
        db.session.commit()


# ==========================
# LOGIN OBRIGATÓRIO
# ==========================
def login_obrigatorio(f):
    @wraps(f)
    def verificar(*args, **kwargs):
        if not session.get("logado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return verificar


# ==========================
# VERIFICAR USUARIO
# ==========================
@app.route("/verificar-usuario", methods=["POST"])
def verificar_usuario():
    usuario = request.form.get("usuario")
    user = Usuario.query.filter_by(usuario=usuario).first()

    return jsonify({
        "existe": user is not None
    })


# ==========================
# LOGIN
# ==========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logado"):
        return redirect("/")

    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        user = Usuario.query.filter_by(usuario=usuario).first()

        if user and check_password_hash(user.senha, senha):
            session.clear()
            session["logado"] = True
            session["usuario"] = user.usuario
            return redirect("/")

        flash("Usuário ou senha inválidos.")
        return redirect("/login")

    return render_template("login.html")


# ==========================
# HOME
# ==========================
@app.route("/")
@login_obrigatorio
def home():
    total_profissionais = Profissional.query.count()
    total_pacientes = Paciente.query.count()
    total_agendamentos = Agendamento.query.count()

    faturamento = db.session.query(db.func.sum(Financeiro.valor)).scalar() or 0

    return render_template(
        "index.html",
        total_profissionais=total_profissionais,
        total_pacientes=total_pacientes,
        total_agendamentos=total_agendamentos,
        faturamento=faturamento
    )


# ==========================
# PROFISSIONAIS
# ==========================
@app.route("/profissionais", methods=["GET", "POST"])
@login_obrigatorio
def profissionais():
    if request.method == "POST":
        profissional_id = request.form.get("profissional_id")

        nome = request.form.get("nome")
        especialidade = request.form.get("especialidade")
        telefone = request.form.get("telefone")
        email = request.form.get("email")

        if profissional_id:
            profissional = Profissional.query.get_or_404(int(profissional_id))
            profissional.nome = nome
            profissional.especialidade = especialidade
            profissional.telefone = telefone
            profissional.email = email
        else:
            profissional = Profissional(
                nome=nome,
                especialidade=especialidade,
                telefone=telefone,
                email=email
            )
            db.session.add(profissional)

        db.session.commit()
        return redirect("/profissionais")

    profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()

    total_profissionais = Profissional.query.count()
    total_especialidades = db.session.query(Profissional.especialidade).distinct().count()
    total_pacientes = Paciente.query.count()

    consultas_hoje = 0
    consultas_pendentes = 0
    proximo_atendimento = None
    taxa_ocupacao = 0

    faturamento_mes = db.session.query(db.func.sum(Financeiro.valor)).filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Recebido"
    ).scalar() or 0

    return render_template(
        "profissionais.html",
        profissionais=profissionais,
        total_profissionais=total_profissionais,
        total_especialidades=total_especialidades,
        total_pacientes=total_pacientes,
        consultas_hoje=consultas_hoje,
        consultas_pendentes=consultas_pendentes,
        proximo_atendimento=proximo_atendimento,
        taxa_ocupacao=taxa_ocupacao,
        faturamento_mes=faturamento_mes
    )


@app.route("/profissionais/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_profissional(id):
    profissional = Profissional.query.get_or_404(id)

    agendamentos_vinculados = Agendamento.query.filter_by(profissional_id=id).count()

    if agendamentos_vinculados > 0:
        return redirect("/profissionais")

    db.session.delete(profissional)
    db.session.commit()

    return redirect("/profissionais")


# ==========================
# PACIENTES
# ==========================
# ==========================
# PACIENTES
# ==========================
@app.route("/pacientes", methods=["GET", "POST"])
@login_obrigatorio
def pacientes():
    if request.method == "POST":
        novo = Paciente(
            nome=request.form.get("nome"),
            data_nascimento=request.form.get("data_nascimento"),
            telefone=request.form.get("telefone"),
            email=request.form.get("email"),
            cpf=request.form.get("cpf"),
            convenio=request.form.get("convenio"),
            plano=request.form.get("plano"),
            observacoes=request.form.get("observacoes")
        )

        db.session.add(novo)
        db.session.commit()

        return redirect("/pacientes")

    lista = Paciente.query.order_by(Paciente.id.desc()).all()

    return render_template("pacientes.html", pacientes=lista)


@app.route("/paciente/editar/<int:id>", methods=["POST"])
@login_obrigatorio
def editar_paciente(id):
    paciente = Paciente.query.get_or_404(id)

    paciente.nome = request.form.get("nome")
    paciente.data_nascimento = request.form.get("data_nascimento")
    paciente.telefone = request.form.get("telefone")
    paciente.email = request.form.get("email")
    paciente.cpf = request.form.get("cpf")
    paciente.convenio = request.form.get("convenio")
    paciente.plano = request.form.get("plano")
    paciente.observacoes = request.form.get("observacoes")

    db.session.commit()

    return redirect("/pacientes")


@app.route("/paciente/excluir/<int:id>")
@login_obrigatorio
def excluir_paciente(id):
    paciente = Paciente.query.get_or_404(id)

    db.session.delete(paciente)
    db.session.commit()

    return redirect("/pacientes")


# ==========================
# AGENDAMENTOS
# ==========================
@app.route("/agendamentos", methods=["GET", "POST"])
@login_obrigatorio
def agendamentos():
    profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()
    servicos = Servico.query.order_by(Servico.nome.asc()).all()

    if request.method == "POST":
        valor_raw = request.form.get("valor") or "0"
        valor = float(valor_raw.replace(",", ".")) if isinstance(valor_raw, str) else float(valor_raw)

        forma_pagamento = request.form.get("forma_pagamento") or "Não informado"
        pagamento_realizado_form = request.form.get("pagamento_realizado") or "nao"
        pagamento_realizado = pagamento_realizado_form == "sim"
        status_agendamento = request.form.get("status") or "Aguardando"

        novo = Agendamento(
            cliente_nome=request.form.get("cliente_nome"),
            cliente_telefone=request.form.get("cliente_telefone"),
            cliente_email=request.form.get("cliente_email"),
            cliente_cpf=request.form.get("cliente_cpf"),
            cliente_data_nascimento=request.form.get("cliente_data_nascimento"),
            observacoes_paciente=request.form.get("observacoes_paciente"),

            profissional_id=int(request.form.get("profissional_id")) if request.form.get("profissional_id") else None,
            servico_id=int(request.form.get("servico_id")) if request.form.get("servico_id") else None,
            data=request.form.get("data"),
            horario=request.form.get("horario"),
            valor=valor,
            forma_pagamento=forma_pagamento,
            pagamento_realizado=pagamento_realizado,
            observacoes_consulta=request.form.get("observacoes_consulta"),
            status=status_agendamento
        )

        db.session.add(novo)
        db.session.flush()

        if novo.valor and novo.valor > 0:
            status_financeiro = "Recebido" if pagamento_realizado else "Pendente"

            financeiro = Financeiro(
                descricao=f"Consulta - {novo.cliente_nome}",
                tipo="Receita",
                categoria="Consultas",
                valor=novo.valor,
                data=datetime.strptime(novo.data, "%Y-%m-%d").date() if novo.data else None,
                data_vencimento=datetime.strptime(novo.data, "%Y-%m-%d").date() if novo.data else None,
                forma_pagamento=forma_pagamento,
                status=status_financeiro,
                agendamento_id=novo.id,
                profissional_id=novo.profissional_id,
                observacoes="Lançamento criado automaticamente pelo agendamento."
            )

            db.session.add(financeiro)

        db.session.commit()

        return redirect("/agendamentos")

    agendamentos_lista = Agendamento.query.order_by(
        Agendamento.data.desc(),
        Agendamento.horario.desc()
    ).all()

    return render_template(
        "agendamentos.html",
        profissionais=profissionais,
        servicos=servicos,
        agendamentos=agendamentos_lista
    )


@app.route("/agendamento/status/<int:id>", methods=["POST"])
@login_obrigatorio
def atualizar_status_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)
    novo_status = request.form.get("status") or "Aguardando"

    agendamento.status = novo_status

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()

    if financeiro:
        if novo_status == "Cancelado":
            financeiro.status = "Cancelado"
        elif agendamento.pagamento_realizado:
            financeiro.status = "Recebido"
        else:
            financeiro.status = "Pendente"

    db.session.commit()

    return redirect("/agendamentos")


# ==========================
# FINANCEIRO
# ==========================
@app.route("/financeiro", methods=["GET", "POST"])
@login_obrigatorio
def financeiro():
    if request.method == "POST":
        descricao = request.form.get("descricao")
        tipo = request.form.get("tipo")
        categoria = request.form.get("categoria")
        valor = request.form.get("valor")
        data = request.form.get("data")
        data_vencimento = request.form.get("data_vencimento")
        forma_pagamento = request.form.get("forma_pagamento")
        status = request.form.get("status")
        paciente_id = request.form.get("paciente_id")
        profissional_id = request.form.get("profissional_id")
        agendamento_id = request.form.get("agendamento_id")
        observacoes = request.form.get("observacoes")

        novo_lancamento = Financeiro(
            descricao=descricao,
            tipo=tipo,
            categoria=categoria,
            valor=float(valor) if valor else 0,
            data=datetime.strptime(data, "%Y-%m-%d").date() if data else datetime.today().date(),
            data_vencimento=datetime.strptime(data_vencimento, "%Y-%m-%d").date() if data_vencimento else None,
            forma_pagamento=forma_pagamento,
            status=status if status else "Recebido",
            paciente_id=int(paciente_id) if paciente_id else None,
            profissional_id=int(profissional_id) if profissional_id else None,
            agendamento_id=int(agendamento_id) if agendamento_id else None,
            observacoes=observacoes
        )

        db.session.add(novo_lancamento)
        db.session.commit()

        return redirect("/financeiro")

    registros = Financeiro.query.order_by(Financeiro.id.desc()).all()

    total_recebido = db.session.query(db.func.sum(Financeiro.valor)).filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Recebido"
    ).scalar() or 0

    total_a_receber = db.session.query(db.func.sum(Financeiro.valor)).filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Pendente"
    ).scalar() or 0

    total_despesas = db.session.query(db.func.sum(Financeiro.valor)).filter(
        Financeiro.tipo == "Despesa",
        Financeiro.status != "Cancelado"
    ).scalar() or 0

    saldo_liquido = total_recebido - total_despesas

    receitas_mes = Financeiro.query.filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Recebido"
    ).count()

    # Gráfico mensal real
    meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    grafico_mensal = []

    for numero_mes in range(1, 13):
        receita_mes = 0
        despesa_mes = 0

        for item in registros:
            if item.data and item.data.month == numero_mes:
                if item.tipo == "Receita" and item.status == "Recebido":
                    receita_mes += item.valor or 0
                elif item.tipo == "Despesa" and item.status != "Cancelado":
                    despesa_mes += item.valor or 0

        lucro_mes = receita_mes - despesa_mes

        grafico_mensal.append({
            "mes": meses[numero_mes - 1],
            "receita": receita_mes,
            "despesa": despesa_mes,
            "lucro": lucro_mes
        })

    maior_valor_grafico = max(
        [max(item["receita"], item["despesa"], item["lucro"]) for item in grafico_mensal],
        default=1
    )

    if maior_valor_grafico <= 0:
        maior_valor_grafico = 1

    # Recebimentos por categoria real
    categorias_receita = {}
    total_categorias = 0

    for item in registros:
        if item.tipo == "Receita" and item.status == "Recebido":
            nome_categoria = item.categoria or "Sem categoria"
            categorias_receita[nome_categoria] = categorias_receita.get(nome_categoria, 0) + (item.valor or 0)
            total_categorias += item.valor or 0

    categorias_receita_lista = []
    for categoria, valor_categoria in categorias_receita.items():
        percentual = (valor_categoria / total_categorias * 100) if total_categorias > 0 else 0
        categorias_receita_lista.append({
            "categoria": categoria,
            "valor": valor_categoria,
            "percentual": round(percentual, 1)
        })

    categorias_receita_lista = sorted(
        categorias_receita_lista,
        key=lambda x: x["valor"],
        reverse=True
    )

    # Contas a receber reais
    contas_a_receber = Financeiro.query.filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Pendente"
    ).order_by(Financeiro.data_vencimento.asc()).limit(5).all()

    # Formas de pagamento reais
    formas_pagamento = {}
    total_formas = 0

    for item in registros:
        if item.tipo == "Receita" and item.status == "Recebido":
            forma = item.forma_pagamento or "Não informado"
            formas_pagamento[forma] = formas_pagamento.get(forma, 0) + (item.valor or 0)
            total_formas += item.valor or 0

    formas_pagamento_lista = []
    for forma, valor_forma in formas_pagamento.items():
        percentual = (valor_forma / total_formas * 100) if total_formas > 0 else 0
        formas_pagamento_lista.append({
            "forma": forma,
            "valor": valor_forma,
            "percentual": round(percentual, 1)
        })

    formas_pagamento_lista = sorted(
        formas_pagamento_lista,
        key=lambda x: x["valor"],
        reverse=True
    )

    pacientes = Paciente.query.order_by(Paciente.nome.asc()).all()
    profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()
    agendamentos = Agendamento.query.order_by(Agendamento.id.desc()).all()

    return render_template(
        "financeiro.html",
        registros=registros,
        total_recebido=total_recebido,
        total_a_receber=total_a_receber,
        total_despesas=total_despesas,
        saldo_liquido=saldo_liquido,
        receitas_mes=receitas_mes,
        grafico_mensal=grafico_mensal,
        maior_valor_grafico=maior_valor_grafico,
        categorias_receita=categorias_receita_lista,
        contas_a_receber=contas_a_receber,
        formas_pagamento=formas_pagamento_lista,
        pacientes=pacientes,
        profissionais=profissionais,
        agendamentos=agendamentos
    )


# ==========================
# FINALIZAR / CANCELAR AGENDAMENTO
# ==========================
@app.route("/finalizar/<int:id>")
@login_obrigatorio
def finalizar_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)
    agendamento.status = "Finalizado"

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()
    if financeiro:
        financeiro.status = "Recebido" if agendamento.pagamento_realizado else "Pendente"

    db.session.commit()
    return redirect("/agendamentos")


@app.route("/cancelar/<int:id>")
@login_obrigatorio
def cancelar_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)
    agendamento.status = "Cancelado"

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()
    if financeiro:
        financeiro.status = "Cancelado"

    db.session.commit()
    return redirect("/agendamentos")


# ==========================
# RECUPERAÇÕES
# ==========================
@app.route("/recuperacoes")
@login_obrigatorio
def recuperacoes():
    pedidos = RecuperacaoSenha.query.all()
    return render_template("recuperacoes.html", pedidos=pedidos)


# ==========================
# FICHA DO PACIENTE
# ==========================
@app.route("/paciente/<int:id>")
@login_obrigatorio
def ficha_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    return render_template("ficha_paciente.html", paciente=paciente)


# ==========================
# LOGOUT
# ==========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ==========================
# INICIAR APP
# ==========================
if __name__ == "__main__":
    app.run(debug=False)