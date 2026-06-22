from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask import jsonify
import random
import string
import os
from flask_migrate import Migrate
from flask import flash



app = Flask(__name__, instance_relative_config=True)
app.secret_key = "clinica_secret_key"

if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:felipegk%4018@localhost:5432/clinica'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


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
    
class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    paciente = db.Column(db.String(100), nullable=False)

    servico_id = db.Column(
        db.Integer,
        db.ForeignKey("servico.id")
    )

    profissional_id = db.Column(
        db.Integer,
        db.ForeignKey("profissional.id")
    )

    profissional = db.relationship(
        "Profissional",
        backref="agendamentos"
    )

    data = db.Column(db.String(20), nullable=False)
    horario = db.Column(db.String(20), nullable=False)

    valor = db.Column(
        db.Float,
        default=0
    )

    status = db.Column(
        db.String(20),
        default="Aguardando"
    )


class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    especialidade = db.Column(db.String(100), nullable=False)


class Paciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(100))


class Financeiro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200))
    valor = db.Column(db.Float, default=0)


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    usuario = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    senha = db.Column(
        db.String(255),
        nullable=False
    )

    tipo = db.Column(
        db.String(20),
        nullable=False,
        default="recepcao"
    )


class RecuperacaoSenha(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    usuario = db.Column(
        db.String(50),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="Pendente"
    )

    nova_senha = db.Column(
        db.String(100)
    )
from flask import request, jsonify

@app.route('/verificar-usuario', methods=['POST'])
def verificar_usuario():

    usuario = request.form.get('usuario')

    encontrado = Usuario.query.filter_by(
        usuario=usuario
    ).first()

    if not encontrado:
        return jsonify({
            "existe": False
        })

    pedido = RecuperacaoSenha(
        usuario=usuario
    )

    db.session.add(pedido)
    db.session.commit()

    return jsonify({
        "existe": True
    })

# ==========================
# LOGIN
# ==========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        user = Usuario.query.filter_by(
            usuario=usuario
        ).first()

        if user and check_password_hash(
            user.senha,
            senha
        ):
            session["logado"] = True
            session["usuario"] = user.usuario

            return redirect("/")

        flash("Usuário ou senha incorretos!", "erro")
        return redirect("/login")

    return render_template("login.html")


# ==========================
# DASHBOARD
# ==========================

@app.route("/")
def home():

    

    if not session.get("logado"):
        return redirect("/login")

    total_profissionais = Profissional.query.count()
    total_pacientes = Paciente.query.count()
    total_agendamentos = Agendamento.query.count()

    faturamento = db.session.query(
        db.func.sum(Financeiro.valor)
    ).scalar()

    if faturamento is None:
        faturamento = 0

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

    return render_template(
        "profissionais.html",
        profissionais=lista
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
            telefone=request.form.get("telefone"),
            email=request.form.get("email")
        )

        db.session.add(novo)
        db.session.commit()

        return redirect("/pacientes")

    lista = Paciente.query.all()

    return render_template(
        "pacientes.html",
        pacientes=lista
    )


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
        # Captura os dados exatamente como estão no 'name' dos inputs do HTML
        novo = Agendamento(
            paciente=request.form.get("paciente"),
            profissional_id=request.form.get("profissional_id"),
            data=request.form.get("data"),
            horario=request.form.get("horario"),
            # Se o seu modelo Agendamento tiver observações:
            observacoes=request.form.get("observacoes") 
        )

        db.session.add(novo)
        db.session.commit()

        return redirect("/agendamentos")

    # Mudei de 'lista' para 'agendamentos' para bater com o {% for ag in agendamentos %} do HTML
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

    total = db.session.query(
        db.func.sum(Financeiro.valor)
    ).scalar()

    if total is None:
        total = 0

    return render_template(
        "financeiro.html",
        registros=registros,
        total=total
    )

@app.route("/finalizar/<int:id>")
def finalizar_agendamento(id):

    if not session.get("logado"):
        return redirect("/login")

    agendamento = Agendamento.query.get_or_404(id)

    db.session.delete(agendamento)
    db.session.commit()

    return redirect("/agendamentos")
# ==========================
# CANCELAR AGENDAMENTO
# ==========================

@app.route("/cancelar/<int:id>")
def cancelar_agendamento(id):

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

@app.route('/recuperacoes')
def recuperacoes():

    pedidos = RecuperacaoSenha.query.all()

    return render_template(
        'recuperacoes.html',
        pedidos=pedidos
    )

@app.route('/atender-recuperacao/<int:id>')
def atender_recuperacao(id):

    pedido = RecuperacaoSenha.query.get(id)

    pedido.status = "Atendido"

    db.session.commit()

    return redirect('/recuperacoes')

@app.route('/excluir-recuperacao/<int:id>')
def excluir_recuperacao(id):

    pedido = RecuperacaoSenha.query.get(id)

    db.session.delete(pedido)

    db.session.commit()

    return redirect('/recuperacoes')

@app.route('/gerar-senha/<int:id>')
def gerar_senha(id):

    pedido = RecuperacaoSenha.query.get(id)

    if not pedido:
        return redirect('/recuperacoes')

    nova_senha = ''.join(
        random.choices(
            string.ascii_letters + string.digits,
            k=8
        )
    )

    usuario = Usuario.query.filter_by(
        usuario=pedido.usuario
    ).first()

    if usuario:

        usuario.senha = generate_password_hash(
            nova_senha
        )

        pedido.status = "Atendido"
        pedido.nova_senha = nova_senha

        db.session.commit()

    return redirect('/recuperacoes')

@app.route('/senha/<int:id>', methods=['GET', 'POST'])
def senha(id):
    pedido = RecuperacaoSenha.query.get(id)

    if request.method == 'POST':

        # se veio do botão "gerar"
        if 'gerar' in request.form:
            nova_senha = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        # se veio digitada manualmente
        else:
            nova_senha = request.form['nova_senha']

        pedido.nova_senha = nova_senha
        pedido.status = "Concluído"

        db.session.commit()
        return redirect('/recuperacoes')

    return render_template('senha.html', pedido=pedido)
@app.route('/cadastro-usuario', methods=['GET', 'POST'])
def cadastro_usuario():
    if request.method == 'POST':
        usuario = request.form['usuario']
        senha = request.form['senha']

        novo = Usuario(
    usuario=usuario,
    senha=generate_password_hash(senha)
    
)
        db.session.add(novo)
        db.session.commit()

        return redirect('/recuperacoes')

    return render_template('cadastro_usuario.html')

@app.route("/chamar/<int:id>")
def chamar(id):

    agendamento = Agendamento.query.get_or_404(id)

    agendamento.status = "Chamado"

    db.session.commit()

    return redirect("/agendamentos")


# ==========================
# INICIAR APP
# ==========================

if __name__ == "__main__":

    with app.app_context():

        db.create_all()

        admin = Usuario.query.filter_by(
            usuario="admin felipe"
        ).first()

        if not admin:

            admin = Usuario(
                usuario="admin felipe",
                senha=generate_password_hash("felipegk@18")
            )

            db.session.add(admin)
            db.session.commit()

            print("ADMIN CRIADO")

        print("BANCO OK")

    app.run(debug=True)