from flask import Flask, render_template, request, redirect, session, jsonify, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import inspect, text
from datetime import datetime, date, timedelta
import os


# ============================================================
# APP CONFIG
# ============================================================

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
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

print("SQLALCHEMY_DATABASE_URI:", app.config["SQLALCHEMY_DATABASE_URI"])

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ============================================================
# MODELOS
# ============================================================

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
    ativo = db.Column(db.Boolean, default=True)

    # Quando o usuário for médico, este campo liga o login ao cadastro do profissional.
    profissional_id = db.Column(db.Integer, db.ForeignKey("profissional.id"), nullable=True)
    profissional = db.relationship("Profissional")


class RecuperacaoSenha(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="Pendente")
    nova_senha = db.Column(db.String(100))


class Autorizacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"))
    paciente = db.relationship("Paciente", backref="autorizacoes")

    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamento.id"))

    data = db.Column(db.String(20))
    texto = db.Column(db.Text)

    assinatura = db.Column(db.Text)
    aceite = db.Column(db.Boolean, default=False)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def login_obrigatorio(f):
    @wraps(f)
    def verificar(*args, **kwargs):
        if not session.get("logado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return verificar


def admin_obrigatorio(f):
    @wraps(f)
    def verificar_admin(*args, **kwargs):
        if not session.get("logado"):
            return redirect(url_for("login"))

        if session.get("tipo") != "admin":
            flash("Acesso permitido apenas para administrador.")
            return redirect(url_for("home"))

        return f(*args, **kwargs)
    return verificar_admin


def usuario_eh_medico():
    return session.get("tipo") == "medico"


def medico_tem_profissional_vinculado():
    return bool(session.get("profissional_id"))


def bloquear_medico_sem_vinculo():
    if usuario_eh_medico() and not medico_tem_profissional_vinculado():
        flash("Seu usuário médico ainda não está vinculado a um profissional. Fale com o administrador.")
        return True
    return False


def medico_pode_acessar_agendamento(agendamento):
    if not usuario_eh_medico():
        return True

    profissional_id = session.get("profissional_id")
    return profissional_id and agendamento.profissional_id == profissional_id


def aplicar_filtro_medico_agendamentos(query):
    if usuario_eh_medico():
        return query.filter(Agendamento.profissional_id == session.get("profissional_id"))
    return query


def converter_data_financeiro(data_texto):
    if data_texto:
        try:
            return datetime.strptime(data_texto, "%Y-%m-%d").date()
        except ValueError:
            return datetime.today().date()
    return datetime.today().date()


def status_financeiro_agendamento(agendamento):
    if agendamento.status == "Cancelado":
        return "Cancelado"
    if agendamento.pagamento_realizado:
        return "Recebido"
    return "Pendente"


def valor_float(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0


def int_ou_none(valor):
    try:
        return int(valor) if valor else None
    except (TypeError, ValueError):
        return None


def primeiro_dia_mes_atual():
    hoje = date.today()
    return date(hoje.year, hoje.month, 1)


def primeiro_dia_proximo_mes():
    hoje = date.today()
    if hoje.month == 12:
        return date(hoje.year + 1, 1, 1)
    return date(hoje.year, hoje.month + 1, 1)


def garantir_colunas_agendamento():
    inspector = inspect(db.engine)
    tabelas = inspector.get_table_names()

    if "agendamento" not in tabelas:
        return

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


def garantir_colunas_usuario():
    inspector = inspect(db.engine)
    tabelas = inspector.get_table_names()

    if "usuario" not in tabelas:
        return

    colunas = [coluna["name"] for coluna in inspector.get_columns("usuario")]

    if "profissional_id" not in colunas:
        db.session.execute(text("ALTER TABLE usuario ADD COLUMN profissional_id INTEGER"))

    if "ativo" not in colunas:
        if db.engine.dialect.name == "postgresql":
            db.session.execute(text("ALTER TABLE usuario ADD COLUMN ativo BOOLEAN DEFAULT TRUE"))
        else:
            db.session.execute(text("ALTER TABLE usuario ADD COLUMN ativo BOOLEAN DEFAULT 1"))

    db.session.commit()


def criar_servicos_padrao():
    if Servico.query.count() > 0:
        return

    servicos_padrao = [
        Servico(nome="Consulta", especialidade="Clínico Geral"),
        Servico(nome="Retorno", especialidade="Clínico Geral"),
        Servico(nome="Avaliação", especialidade="Avaliação"),
        Servico(nome="Procedimento", especialidade="Procedimento"),
        Servico(nome="Exame", especialidade="Exame"),
    ]

    nomes_existentes = {item.nome.lower().strip() for item in servicos_padrao}

    especialidades = db.session.query(Profissional.especialidade).distinct().all()
    for (especialidade,) in especialidades:
        if especialidade and especialidade.lower().strip() not in nomes_existentes:
            servicos_padrao.append(
                Servico(nome=especialidade, especialidade=especialidade)
            )

    db.session.add_all(servicos_padrao)
    db.session.commit()


# ============================================================
# PROTEÇÃO GLOBAL DE LOGIN
# ============================================================

@app.before_request
def proteger_rotas():
    rotas_livres = [
        "login",
        "static",
        "verificar_usuario",
    ]

    if request.endpoint in rotas_livres:
        return

    if not session.get("logado"):
        return redirect("/login")


@app.before_request
def bloquear_telas_medico():
    if not session.get("logado"):
        return

    if session.get("tipo") != "medico":
        return

    rotas_permitidas_medico = [
        "home",
        "logout",
        "agendamentos",
        "visualizar_agendamento",
        "atualizar_status_agendamento",
        "finalizar_agendamento",
        "cancelar_agendamento",
        "editar_agendamento",
        "static",
    ]

    if request.endpoint not in rotas_permitidas_medico:
        flash("Médico não tem permissão para acessar essa área.")
        return redirect(url_for("agendamentos"))


# ============================================================
# BANCO / INICIALIZAÇÃO
# ============================================================

with app.app_context():
    db.create_all()
    garantir_colunas_agendamento()
    garantir_colunas_usuario()
    criar_servicos_padrao()


# ============================================================
# LOGIN / LOGOUT
# ============================================================

@app.route("/verificar-usuario", methods=["POST"])
def verificar_usuario():
    usuario = request.form.get("usuario")
    user = Usuario.query.filter_by(usuario=usuario).first()

    return jsonify({
        "existe": user is not None
    })


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logado"):
        return redirect("/")

    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        user = Usuario.query.filter_by(usuario=usuario).first()

        if user and check_password_hash(user.senha, senha):
            if getattr(user, "ativo", True) is False:
                flash("Este usuário está bloqueado. Fale com o administrador.")
                return redirect("/login")

            session.clear()
            session["logado"] = True
            session["usuario"] = user.usuario
            session["tipo"] = user.tipo or "recepcao"
            session["usuario_id"] = user.id
            session["profissional_id"] = user.profissional_id
            return redirect("/")

        flash("Usuário ou senha inválidos.")
        return redirect("/login")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@login_obrigatorio
def home():
    if bloquear_medico_sem_vinculo():
        return redirect(url_for("logout"))

    if usuario_eh_medico():
        profissional_id = session.get("profissional_id")
        total_profissionais = 1
        total_pacientes = Paciente.query.join(Agendamento, Agendamento.paciente_id == Paciente.id).filter(
            Agendamento.profissional_id == profissional_id
        ).distinct().count()
        total_agendamentos = Agendamento.query.filter_by(profissional_id=profissional_id).count()

        faturamento = db.session.query(db.func.sum(Financeiro.valor)).filter(
            Financeiro.tipo == "Receita",
            Financeiro.status == "Recebido",
            Financeiro.profissional_id == profissional_id
        ).scalar() or 0
    else:
        total_profissionais = Profissional.query.count()
        total_pacientes = Paciente.query.count()
        total_agendamentos = Agendamento.query.count()

        faturamento = db.session.query(db.func.sum(Financeiro.valor)).filter(
            Financeiro.tipo == "Receita",
            Financeiro.status == "Recebido"
        ).scalar() or 0

    return render_template(
        "index.html",
        total_profissionais=total_profissionais,
        total_pacientes=total_pacientes,
        total_agendamentos=total_agendamentos,
        faturamento=faturamento
    )


# ============================================================
# PROFISSIONAIS
# ============================================================

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

    lista_profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()

    total_profissionais = Profissional.query.count()
    total_especialidades = db.session.query(Profissional.especialidade).distinct().count()
    total_pacientes = Paciente.query.count()

    consultas_hoje = 0
    consultas_pendentes = 0
    proximo_atendimento = None
    taxa_ocupacao = 0

    faturamento_mes = db.session.query(db.func.sum(Financeiro.valor)).filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Recebido",
        Financeiro.data >= primeiro_dia_mes_atual(),
        Financeiro.data < primeiro_dia_proximo_mes()
    ).scalar() or 0

    return render_template(
        "profissionais.html",
        profissionais=lista_profissionais,
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


# ============================================================
# PACIENTES
# ============================================================

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

    if usuario_eh_medico():
        lista = Paciente.query.join(Agendamento, Agendamento.paciente_id == Paciente.id).filter(
            Agendamento.profissional_id == session.get("profissional_id")
        ).distinct().order_by(Paciente.id.desc()).all()
    else:
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


@app.route("/paciente/excluir/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def excluir_paciente(id):
    paciente = Paciente.query.get_or_404(id)

    db.session.delete(paciente)
    db.session.commit()

    return redirect("/pacientes")


@app.route("/paciente/<int:id>")
@login_obrigatorio
def ficha_paciente(id):
    paciente = Paciente.query.get_or_404(id)

    if usuario_eh_medico():
        tem_vinculo = Agendamento.query.filter_by(
            paciente_id=paciente.id,
            profissional_id=session.get("profissional_id")
        ).first()

        if not tem_vinculo:
            flash("Você não tem permissão para acessar este paciente.")
            return redirect(url_for("pacientes"))

    return render_template("ficha_paciente.html", paciente=paciente)


# ============================================================
# AGENDAMENTOS
# ============================================================

@app.route("/agendamentos", methods=["GET", "POST"])
@login_obrigatorio
def agendamentos():
    if bloquear_medico_sem_vinculo():
        return redirect(url_for("logout"))

    if request.method == "POST":
        pagamento_realizado = request.form.get("pagamento_realizado") == "sim"
        profissional_id_form = int_ou_none(request.form.get("profissional_id"))

        if usuario_eh_medico():
            profissional_id_form = session.get("profissional_id")

        novo_agendamento = Agendamento(
            cliente_nome=request.form.get("cliente_nome"),
            cliente_telefone=request.form.get("cliente_telefone"),
            cliente_email=request.form.get("cliente_email"),
            cliente_cpf=request.form.get("cliente_cpf"),
            cliente_data_nascimento=request.form.get("cliente_data_nascimento"),
            observacoes_paciente=request.form.get("observacoes_paciente"),
            profissional_id=profissional_id_form,
            servico_id=int_ou_none(request.form.get("servico_id")),
            data=request.form.get("data"),
            horario=request.form.get("horario"),
            valor=valor_float(request.form.get("valor")),
            forma_pagamento=request.form.get("forma_pagamento") or "Não informado",
            pagamento_realizado=pagamento_realizado,
            status=request.form.get("status") or "Aguardando",
            observacoes_consulta=request.form.get("observacoes_consulta")
        )

        db.session.add(novo_agendamento)
        db.session.commit()

        financeiro = Financeiro(
            agendamento_id=novo_agendamento.id,
            descricao=f"Consulta - {novo_agendamento.cliente_nome or 'Paciente'}",
            tipo="Receita",
            categoria="Consulta",
            valor=novo_agendamento.valor,
            data=converter_data_financeiro(novo_agendamento.data),
            data_vencimento=converter_data_financeiro(novo_agendamento.data),
            forma_pagamento=novo_agendamento.forma_pagamento,
            status=status_financeiro_agendamento(novo_agendamento),
            profissional_id=novo_agendamento.profissional_id,
            observacoes=novo_agendamento.observacoes_consulta
        )

        db.session.add(financeiro)
        db.session.commit()

        return redirect("/agendamentos")

    profissional_filtro = request.args.get("profissional_id", "")
    periodo_filtro = request.args.get("periodo", "todas")

    query = aplicar_filtro_medico_agendamentos(Agendamento.query)

    if profissional_filtro and not usuario_eh_medico():
        query = query.filter(Agendamento.profissional_id == int(profissional_filtro))

    if usuario_eh_medico():
        profissional_filtro = str(session.get("profissional_id"))

    hoje = date.today()

    if periodo_filtro == "hoje":
        query = query.filter(Agendamento.data == hoje.isoformat())

    elif periodo_filtro == "amanha":
        amanha = hoje + timedelta(days=1)
        query = query.filter(Agendamento.data == amanha.isoformat())

    elif periodo_filtro == "semana":
        fim_semana = hoje + timedelta(days=7)
        query = query.filter(
            Agendamento.data >= hoje.isoformat(),
            Agendamento.data <= fim_semana.isoformat()
        )

    elif periodo_filtro == "mes":
        inicio_mes = hoje.replace(day=1)

        if hoje.month == 12:
            proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
        else:
            proximo_mes = hoje.replace(month=hoje.month + 1, day=1)

        query = query.filter(
            Agendamento.data >= inicio_mes.isoformat(),
            Agendamento.data < proximo_mes.isoformat()
        )

    lista_agendamentos = query.order_by(
        Agendamento.data.asc(),
        Agendamento.horario.asc()
    ).all()

    if usuario_eh_medico():
        profissionais = Profissional.query.filter_by(id=session.get("profissional_id")).all()
    else:
        profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()
    servicos = Servico.query.order_by(Servico.nome.asc()).all()

    return render_template(
        "agendamentos.html",
        agendamentos=lista_agendamentos,
        profissionais=profissionais,
        servicos=servicos,
        profissional_filtro=profissional_filtro,
        periodo_filtro=periodo_filtro
    )


@app.route("/agendamento/status/<int:id>", methods=["POST"])
@login_obrigatorio
def atualizar_status_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)

    if not medico_pode_acessar_agendamento(agendamento):
        flash("Você não tem permissão para alterar este agendamento.")
        return redirect(url_for("agendamentos"))

    agendamento.status = request.form.get("status") or "Aguardando"

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()

    if financeiro:
        financeiro.status = status_financeiro_agendamento(agendamento)

    db.session.commit()

    return redirect("/agendamentos")


@app.route("/agendamento/<int:id>")
@login_obrigatorio
def visualizar_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)

    if not medico_pode_acessar_agendamento(agendamento):
        return jsonify({"erro": "Sem permissão para acessar este agendamento."}), 403

    return jsonify({
        "id": agendamento.id,
        "cliente_nome": agendamento.cliente_nome,
        "cliente_telefone": agendamento.cliente_telefone,
        "cliente_email": agendamento.cliente_email,
        "cliente_cpf": agendamento.cliente_cpf,
        "cliente_data_nascimento": agendamento.cliente_data_nascimento,
        "observacoes_paciente": agendamento.observacoes_paciente,
        "profissional": agendamento.profissional.nome if agendamento.profissional else "",
        "servico": agendamento.servico.nome if agendamento.servico else "",
        "data": agendamento.data,
        "horario": agendamento.horario,
        "valor": agendamento.valor,
        "forma_pagamento": agendamento.forma_pagamento,
        "pagamento_realizado": "Sim" if agendamento.pagamento_realizado else "Não",
        "status": agendamento.status,
        "observacoes_consulta": agendamento.observacoes_consulta
    })


@app.route("/agendamento/editar/<int:id>", methods=["POST"])
@login_obrigatorio
def editar_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)

    if not medico_pode_acessar_agendamento(agendamento):
        flash("Você não tem permissão para editar este agendamento.")
        return redirect(url_for("agendamentos"))

    agendamento.cliente_nome = request.form.get("cliente_nome")
    agendamento.cliente_telefone = request.form.get("cliente_telefone")
    agendamento.cliente_email = request.form.get("cliente_email")
    agendamento.cliente_cpf = request.form.get("cliente_cpf")
    agendamento.cliente_data_nascimento = request.form.get("cliente_data_nascimento")
    agendamento.observacoes_paciente = request.form.get("observacoes_paciente")
    if usuario_eh_medico():
        agendamento.profissional_id = session.get("profissional_id")
    else:
        agendamento.profissional_id = int_ou_none(request.form.get("profissional_id"))
    agendamento.servico_id = int_ou_none(request.form.get("servico_id"))
    agendamento.data = request.form.get("data")
    agendamento.horario = request.form.get("horario")
    agendamento.valor = valor_float(request.form.get("valor"))
    agendamento.forma_pagamento = request.form.get("forma_pagamento") or "Não informado"
    agendamento.pagamento_realizado = request.form.get("pagamento_realizado") == "sim"
    agendamento.status = request.form.get("status") or "Aguardando"
    agendamento.observacoes_consulta = request.form.get("observacoes_consulta")

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()

    if not financeiro:
        financeiro = Financeiro(agendamento_id=agendamento.id)
        db.session.add(financeiro)

    financeiro.descricao = f"Consulta - {agendamento.cliente_nome or 'Paciente'}"
    financeiro.tipo = "Receita"
    financeiro.categoria = "Consulta"
    financeiro.valor = agendamento.valor
    financeiro.data = converter_data_financeiro(agendamento.data)
    financeiro.data_vencimento = converter_data_financeiro(agendamento.data)
    financeiro.forma_pagamento = agendamento.forma_pagamento
    financeiro.status = status_financeiro_agendamento(agendamento)
    financeiro.profissional_id = agendamento.profissional_id
    financeiro.observacoes = agendamento.observacoes_consulta

    db.session.commit()

    return redirect("/agendamentos")


@app.route("/agendamento/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)

    if usuario_eh_medico():
        flash("Médico não pode excluir agendamento. Peça para a recepção ou administrador.")
        return redirect(url_for("agendamentos"))

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()

    if financeiro:
        db.session.delete(financeiro)

    db.session.delete(agendamento)
    db.session.commit()

    return redirect("/agendamentos")


@app.route("/finalizar/<int:id>")
@login_obrigatorio
def finalizar_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)

    if not medico_pode_acessar_agendamento(agendamento):
        flash("Você não tem permissão para finalizar este agendamento.")
        return redirect(url_for("agendamentos"))

    agendamento.status = "Finalizado"

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()

    if financeiro:
        financeiro.status = status_financeiro_agendamento(agendamento)

    db.session.commit()
    return redirect("/agendamentos")


@app.route("/cancelar/<int:id>")
@login_obrigatorio
def cancelar_agendamento(id):
    agendamento = Agendamento.query.get_or_404(id)

    if not medico_pode_acessar_agendamento(agendamento):
        flash("Você não tem permissão para cancelar este agendamento.")
        return redirect(url_for("agendamentos"))

    agendamento.status = "Cancelado"

    financeiro = Financeiro.query.filter_by(agendamento_id=agendamento.id).first()

    if financeiro:
        financeiro.status = "Cancelado"

    db.session.commit()
    return redirect("/agendamentos")


# ============================================================
# FINANCEIRO
# ============================================================

@app.route("/financeiro", methods=["GET", "POST"])
@login_obrigatorio
def financeiro():
    if usuario_eh_medico():
        flash("Médico não tem acesso ao financeiro.")
        return redirect(url_for("agendamentos"))

    if request.method == "POST":
        financeiro_id = request.form.get("financeiro_id")

        if financeiro_id:
            lancamento = Financeiro.query.get_or_404(int(financeiro_id))
        else:
            lancamento = Financeiro()

        lancamento.descricao = request.form.get("descricao")
        lancamento.tipo = request.form.get("tipo")
        lancamento.categoria = request.form.get("categoria")
        lancamento.valor = valor_float(request.form.get("valor"))
        lancamento.data = datetime.strptime(request.form.get("data"), "%Y-%m-%d").date() if request.form.get("data") else datetime.today().date()
        lancamento.data_vencimento = datetime.strptime(request.form.get("data_vencimento"), "%Y-%m-%d").date() if request.form.get("data_vencimento") else None
        lancamento.forma_pagamento = request.form.get("forma_pagamento")
        lancamento.status = request.form.get("status") or "Recebido"
        lancamento.paciente_id = int_ou_none(request.form.get("paciente_id"))
        lancamento.profissional_id = int_ou_none(request.form.get("profissional_id"))
        lancamento.agendamento_id = int_ou_none(request.form.get("agendamento_id"))
        lancamento.observacoes = request.form.get("observacoes")

        if not financeiro_id:
            db.session.add(lancamento)

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

    receitas_mes = db.session.query(db.func.sum(Financeiro.valor)).filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Recebido",
        Financeiro.data >= primeiro_dia_mes_atual(),
        Financeiro.data < primeiro_dia_proximo_mes()
    ).scalar() or 0

    pacientes = Paciente.query.order_by(Paciente.nome.asc()).all()
    profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()
    agendamentos_lista = Agendamento.query.order_by(Agendamento.id.desc()).all()

    return render_template(
        "financeiro.html",
        registros=registros,
        total_recebido=total_recebido,
        total_a_receber=total_a_receber,
        total_despesas=total_despesas,
        saldo_liquido=saldo_liquido,
        receitas_mes=receitas_mes,
        pacientes=pacientes,
        profissionais=profissionais,
        agendamentos=agendamentos_lista
    )


@app.route("/financeiro/visualizar/<int:id>")
@login_obrigatorio
def visualizar_financeiro(id):
    if usuario_eh_medico():
        return jsonify({"erro": "Médico não tem acesso ao financeiro."}), 403

    lancamento = Financeiro.query.get_or_404(id)

    return jsonify({
        "id": lancamento.id,
        "descricao": lancamento.descricao,
        "tipo": lancamento.tipo,
        "categoria": lancamento.categoria or "",
        "valor": lancamento.valor or 0,
        "data": lancamento.data.strftime("%Y-%m-%d") if lancamento.data else "",
        "data_formatada": lancamento.data.strftime("%d/%m/%Y") if lancamento.data else "",
        "data_vencimento": lancamento.data_vencimento.strftime("%Y-%m-%d") if lancamento.data_vencimento else "",
        "data_vencimento_formatada": lancamento.data_vencimento.strftime("%d/%m/%Y") if lancamento.data_vencimento else "",
        "forma_pagamento": lancamento.forma_pagamento or "",
        "status": lancamento.status or "",
        "paciente": lancamento.paciente.nome if lancamento.paciente else "",
        "paciente_id": lancamento.paciente_id or "",
        "profissional": lancamento.profissional.nome if lancamento.profissional else "",
        "profissional_id": lancamento.profissional_id or "",
        "agendamento_id": lancamento.agendamento_id or "",
        "observacoes": lancamento.observacoes or "",
        "criado_em": lancamento.criado_em.strftime("%d/%m/%Y %H:%M") if lancamento.criado_em else ""
    })


@app.route("/financeiro/editar/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def editar_financeiro(id):
    if usuario_eh_medico():
        flash("Médico não tem acesso ao financeiro.")
        return redirect(url_for("agendamentos"))

    lancamento = Financeiro.query.get_or_404(id)

    if request.method == "POST":
        lancamento.descricao = request.form.get("descricao")
        lancamento.tipo = request.form.get("tipo")
        lancamento.categoria = request.form.get("categoria")
        lancamento.valor = valor_float(request.form.get("valor"))
        lancamento.data = datetime.strptime(request.form.get("data"), "%Y-%m-%d").date() if request.form.get("data") else datetime.today().date()
        lancamento.data_vencimento = datetime.strptime(request.form.get("data_vencimento"), "%Y-%m-%d").date() if request.form.get("data_vencimento") else None
        lancamento.forma_pagamento = request.form.get("forma_pagamento")
        lancamento.status = request.form.get("status") or "Recebido"
        lancamento.paciente_id = int_ou_none(request.form.get("paciente_id"))
        lancamento.profissional_id = int_ou_none(request.form.get("profissional_id"))
        lancamento.agendamento_id = int_ou_none(request.form.get("agendamento_id"))
        lancamento.observacoes = request.form.get("observacoes")

        db.session.commit()
        return redirect("/financeiro")

    return redirect("/financeiro")


@app.route("/financeiro/excluir/<int:id>", methods=["POST", "GET"])
@login_obrigatorio
def excluir_financeiro(id):
    if usuario_eh_medico():
        flash("Médico não tem acesso ao financeiro.")
        return redirect(url_for("agendamentos"))

    lancamento = Financeiro.query.get_or_404(id)

    db.session.delete(lancamento)
    db.session.commit()

    return redirect("/financeiro")



# ============================================================
# USUÁRIOS / PERMISSÕES
# ============================================================

@app.route("/usuarios", methods=["GET", "POST"])
@admin_obrigatorio
def usuarios():
    if request.method == "POST":
        usuario_id = request.form.get("usuario_id")
        nome_usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""
        tipo = request.form.get("tipo") or "recepcao"
        profissional_id = int_ou_none(request.form.get("profissional_id"))
        ativo = request.form.get("ativo") == "sim"

        if tipo != "medico":
            profissional_id = None

        if tipo == "medico" and not profissional_id:
            flash("Para usuário do tipo médico, selecione o profissional vinculado.")
            return redirect(url_for("usuarios"))

        if not nome_usuario:
            flash("Informe o nome de usuário.")
            return redirect(url_for("usuarios"))

        usuario_existente = Usuario.query.filter_by(usuario=nome_usuario).first()

        if usuario_id:
            usuario_obj = Usuario.query.get_or_404(int(usuario_id))

            if usuario_existente and usuario_existente.id != usuario_obj.id:
                flash("Já existe outro usuário com esse login.")
                return redirect(url_for("usuarios"))

            usuario_obj.usuario = nome_usuario
            usuario_obj.tipo = tipo
            usuario_obj.profissional_id = profissional_id
            usuario_obj.ativo = ativo

            if senha.strip():
                usuario_obj.senha = generate_password_hash(senha.strip())
        else:
            if usuario_existente:
                flash("Já existe um usuário com esse login.")
                return redirect(url_for("usuarios"))

            if not senha.strip():
                flash("Informe uma senha para o novo usuário.")
                return redirect(url_for("usuarios"))

            usuario_obj = Usuario(
                usuario=nome_usuario,
                senha=generate_password_hash(senha.strip()),
                tipo=tipo,
                profissional_id=profissional_id,
                ativo=ativo
            )
            db.session.add(usuario_obj)

        db.session.commit()
        flash("Usuário salvo com sucesso.")
        return redirect(url_for("usuarios"))

    lista_usuarios = Usuario.query.order_by(Usuario.id.desc()).all()
    profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()

    return render_template(
        "usuarios.html",
        usuarios=lista_usuarios,
        profissionais=profissionais
    )


@app.route("/usuarios/excluir/<int:id>", methods=["POST"])
@admin_obrigatorio
def excluir_usuario(id):
    usuario_obj = Usuario.query.get_or_404(id)

    if session.get("usuario_id") == usuario_obj.id:
        flash("Você não pode excluir o próprio usuário logado.")
        return redirect(url_for("usuarios"))

    db.session.delete(usuario_obj)
    db.session.commit()
    flash("Usuário excluído com sucesso.")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/bloquear/<int:id>", methods=["POST"])
@admin_obrigatorio
def bloquear_usuario(id):
    usuario_obj = Usuario.query.get_or_404(id)

    if session.get("usuario_id") == usuario_obj.id:
        flash("Você não pode bloquear o próprio usuário logado.")
        return redirect(url_for("usuarios"))

    usuario_obj.ativo = not bool(getattr(usuario_obj, "ativo", True))
    db.session.commit()
    flash("Status do usuário atualizado.")
    return redirect(url_for("usuarios"))


# ============================================================
# RECUPERAÇÕES
# ============================================================

@app.route("/recuperacoes")
@login_obrigatorio
def recuperacoes():
    pedidos = RecuperacaoSenha.query.all()
    return render_template("recuperacoes.html", pedidos=pedidos)


# ============================================================
# INICIAR APP
# ============================================================

if __name__ == "__main__":
    app.run(debug=False)
