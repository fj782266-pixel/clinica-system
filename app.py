from flask import Flask, render_template, request, redirect, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import os
from datetime import datetime
from sqlalchemy import func


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
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200))
    valor = db.Column(db.Float, default=0)


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
@app.route('/verificar-usuario', methods=['POST'])
def verificar_usuario():
    usuario = request.form.get('usuario')

    encontrado = Usuario.query.filter_by(usuario=usuario).first()

    if not encontrado:
        return jsonify({"existe": False})

    pedido = RecuperacaoSenha(usuario=usuario)
    db.session.add(pedido)
    db.session.commit()

    return jsonify({"existe": True})


# ==========================
# LOGIN
# ==========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        user = Usuario.query.filter_by(usuario=usuario).first()

          # 👇 COLOCA AQUI
        print("USER:", user)
        print("USUARIO DIGITADO:", usuario)
        print("SENHA DIGITADA:", senha)

        if user and check_password_hash(user.senha, senha):
            session.clear()
            session["logado"] = True
            session["usuario"] = user.usuario
            session.permanent = True
            return redirect("/")

        flash("Usuário ou senha incorretos!", "erro")
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

    lista = Profissional.query.all()

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
                valor=novo.valor
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
        novo = Financeiro(
            descricao=request.form.get("descricao"),
            valor=float(request.form.get("valor"))
        )

        db.session.add(novo)
        db.session.commit()

        return redirect("/financeiro")

    registros = Financeiro.query.all()
    total = db.session.query(db.func.sum(Financeiro.valor)).scalar() or 0

    return render_template("financeiro.html", registros=registros, total=total)


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