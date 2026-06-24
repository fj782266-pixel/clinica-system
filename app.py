from flask import Flask, render_template, request, redirect, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import os


# ==========================
# APP CONFIG
# ==========================
app = Flask(__name__, instance_relative_config=True)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-inseguro")

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

    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"))
    paciente = db.relationship("Paciente", backref="agendamentos")

    profissional_id = db.Column(db.Integer, db.ForeignKey("profissional.id"))
    profissional = db.relationship("Profissional", backref="agendamentos")

    servico_id = db.Column(db.Integer, db.ForeignKey("servico.id"))

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
    estado_civil = db.Column(db.String(50))
    telefone = db.Column(db.String(20))
    cidade = db.Column(db.String(100))
    endereco = db.Column(db.String(200))
    idade = db.Column(db.Integer)
    profissao = db.Column(db.String(100))
    email = db.Column(db.String(120))
    sexo = db.Column(db.String(20))


class Autorizacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"))
    paciente = db.relationship("Paciente", backref="autorizacoes")

    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamento.id"))

    data = db.Column(db.String(20))
    texto = db.Column(db.Text)

    assinatura = db.Column(db.Text)  # ou LargeBinary
    aceite = db.Column(db.Boolean, default=False)
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

    return render_template("profissionais.html", profissionais=lista)


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
            telefone=request.form.get("telefone"),
            email=request.form.get("email")
        )

        db.session.add(novo)
        db.session.commit()

        return redirect("/pacientes")

    lista = Paciente.query.all()

    return render_template("pacientes.html", pacientes=lista)


# ==========================
# AGENDAMENTOS
# ==========================
@app.route("/agendamentos", methods=["GET", "POST"])
def agendamentos():
    if not session.get("logado"):
        return redirect("/login")

    profissionais = Profissional.query.all()
    servicos = Servico.query.all()

    if request.method == "POST":
        novo = Agendamento(
            paciente=request.form.get("paciente"),
            profissional_id=request.form.get("profissional_id"),
            servico_id=request.form.get("servico_id"),
            data=request.form.get("data"),
            horario=request.form.get("horario")
        )

        db.session.add(novo)
        db.session.commit()

        return redirect("/agendamentos")

    agendamentos_lista = Agendamento.query.all()

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
        db.create_all()

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