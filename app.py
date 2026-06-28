from flask import Flask, render_template, request, redirect, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import os
from datetime import datetime
from sqlalchemy import func
from datetime import datetime


# ==========================
# APP CONFIG
# ==========================
app = Flask(__name__, instance_relative_config=True)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-inseguro")

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

db_url = os.environ.get("DATABASE_URL")

# se NÃO tiver variável (local), usa sqlite
if not db_url:
    db_url = "sqlite:///clinica.db"
else:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

print("SQLALCHEMY_DATABASE_URI:", app.config['SQLALCHEMY_DATABASE_URI'])
db = SQLAlchemy(app)
migrate = Migrate(app, db)

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


with app.app_context():
    db.create_all()
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
def home():
    if not session.get("logado"):
        return redirect("/login")

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
def profissionais():
    if not session.get("logado"):
        return redirect("/login")

    if request.method == "POST":
        novo = Profissional(
            nome=request.form.get("nome"),
            especialidade=request.form.get("especialidade"),
            telefone=request.form.get("telefone"),
            email=request.form.get("email")
        )

        db.session.add(novo)
        db.session.commit()

        return redirect("/profissionais")

    lista = Profissional.query.order_by(Profissional.nome.asc()).all()

    total_profissionais = Profissional.query.count()
    total_pacientes = Paciente.query.count()

    total_especialidades = db.session.query(
        func.count(func.distinct(Profissional.especialidade))
    ).scalar() or 0

    hoje = datetime.now().strftime("%Y-%m-%d")

    consultas_hoje = Agendamento.query.filter_by(data=hoje).count()

    consultas_pendentes = Agendamento.query.filter(
        Agendamento.status.in_(["Aguardando", "Pendente"])
    ).count()

    proximo_atendimento = Agendamento.query.filter(
        Agendamento.data >= hoje
    ).order_by(
        Agendamento.data.asc(),
        Agendamento.horario.asc()
    ).first()

    faturamento_mes = db.session.query(
        func.sum(Financeiro.valor)
    ).scalar() or 0

    capacidade_dia = 20
    taxa_ocupacao = int((consultas_hoje / capacidade_dia) * 100) if capacidade_dia else 0

    return render_template(
        "profissionais.html",
        profissionais=lista,
        total_profissionais=total_profissionais,
        total_especialidades=total_especialidades,
        consultas_hoje=consultas_hoje,
        faturamento_mes=faturamento_mes,
        total_pacientes=total_pacientes,
        proximo_atendimento=proximo_atendimento,
        taxa_ocupacao=taxa_ocupacao,
        consultas_pendentes=consultas_pendentes
    )


# ==========================
# PACIENTES
# ==========================
@app.route("/pacientes", methods=["GET", "POST"])
def pacientes():
    if not session.get("logado"):
        return redirect("/login")

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


# ==========================
# AGENDAMENTOS
# ==========================
@app.route("/agendamentos", methods=["GET", "POST"])
def agendamentos():
    if not session.get("logado"):
        return redirect("/login")

    profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()
    servicos = Servico.query.order_by(Servico.nome.asc()).all()

    if request.method == "POST":
        valor = request.form.get("valor") or 0

        novo = Agendamento(
            cliente_nome=request.form.get("cliente_nome"),
            cliente_telefone=request.form.get("cliente_telefone"),
            cliente_email=request.form.get("cliente_email"),
            cliente_cpf=request.form.get("cliente_cpf"),
            cliente_data_nascimento=request.form.get("cliente_data_nascimento"),
            observacoes_paciente=request.form.get("observacoes_paciente"),

            profissional_id=request.form.get("profissional_id"),
            servico_id=request.form.get("servico_id"),
            data=request.form.get("data"),
            horario=request.form.get("horario"),
            valor=float(valor),
            observacoes_consulta=request.form.get("observacoes_consulta"),
            status="Aguardando"
        )

        db.session.add(novo)

        if novo.valor and novo.valor > 0:
            financeiro = Financeiro(
    descricao=f"Consulta - {novo.cliente_nome}",
    tipo="Receita",
    categoria="Consultas",
    valor=novo.valor,
    data=datetime.strptime(novo.data, "%Y-%m-%d").date() if novo.data else None,
    forma_pagamento="Não informado",
    status="Pendente",
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


# ==========================
# FINANCEIRO
# ==========================
@app.route("/financeiro", methods=["GET", "POST"])
def financeiro():
    if not session.get("logado"):
        return redirect("/login")

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
            data=datetime.strptime(data, "%Y-%m-%d").date() if data else None,
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

    total_recebido = db.session.query(
        db.func.sum(Financeiro.valor)
    ).filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Recebido"
    ).scalar() or 0

    total_a_receber = db.session.query(
        db.func.sum(Financeiro.valor)
    ).filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Pendente"
    ).scalar() or 0

    total_despesas = db.session.query(
        db.func.sum(Financeiro.valor)
    ).filter(
        Financeiro.tipo == "Despesa"
    ).scalar() or 0

    saldo_liquido = total_recebido - total_despesas

    receitas_mes = Financeiro.query.filter(
        Financeiro.tipo == "Receita",
        Financeiro.status == "Recebido"
    ).count()

    pacientes = Paciente.query.order_by(Paciente.nome.asc()).all()
    profissionais = Profissional.query.order_by(Profissional.nome.asc()).all()
    agendamentos = Agendamento.query.order_by(Agendamento.id.desc()).all()

    return render_template(
        "financeiro.html",
        registros=registros,
        total=total_recebido,
        total_recebido=total_recebido,
        total_a_receber=total_a_receber,
        total_despesas=total_despesas,
        saldo_liquido=saldo_liquido,
        receitas_mes=receitas_mes,
        pacientes=pacientes,
        profissionais=profissionais,
        agendamentos=agendamentos
    )

# ==========================
# FINALIZAR / CANCELAR
# ==========================
@app.route("/finalizar/<int:id>")
@app.route("/cancelar/<int:id>")
def remover_agendamento(id):
    if not session.get("logado"):
        return redirect("/login")

    agendamento = Agendamento.query.get_or_404(id)

    db.session.delete(agendamento)
    db.session.commit()

    return redirect("/agendamentos")


# ==========================
# LOGOUT
# ==========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ==========================
# RECUPERAÇÃO
# ==========================
@app.route('/recuperacoes')
def recuperacoes():
    pedidos = RecuperacaoSenha.query.all()
    return render_template('recuperacoes.html', pedidos=pedidos)

@app.route("/init-db")
def init_db():
    with app.app_context():
        db.create_all()
    return "DB criado com sucesso"

@app.route("/criar-admin")
def criar_admin():
    admin = Usuario.query.filter_by(usuario="admin felipe").first()

    if not admin:
        admin = Usuario(
            usuario="admin felipe",
            senha=generate_password_hash("felipegk@18")
        )
        db.session.add(admin)
        db.session.commit()

    return "ok"

@app.route("/paciente/<int:id>")
def ficha_paciente(id):
    paciente = Paciente.query.get_or_404(id)
    return render_template("ficha_paciente.html", paciente=paciente)
# ==========================
# INICIAR APP
# ==========================
if __name__ == "__main__":

    with app.app_context():


        admin = Usuario.query.filter_by(usuario="admin felipe").first()

        if not admin:
            admin = Usuario(
                usuario="admin felipe",
                senha=generate_password_hash("felipegk@18")
            )
            db.session.add(admin)
            db.session.commit()

        print("BANCO OK")

    app.run(debug=True)