#importações de blibliotecas
# Importações de bibliotecas
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail
import re
import dns.resolver
from apscheduler.schedulers.background import BackgroundScheduler
from flask_socketio import SocketIO, emit
from mailjet_rest import Client
import requests, os, uuid

app = Flask(__name__)

GOOGLE_MAPS_API_KEY = 'AIzaSyCFg28W1NRnx48tyCEGVQpmPmVxOBoxOtQ'
GEOCODE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'

# Configurações da aplicação
app.config['SECRET_KEY'] = 'random_string'
app.config['MAIL_SERVER'] = 'smtp.example.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'your-email@example.com'
app.config['MAIL_PASSWORD'] = 'your-password'
mail = Mail(app)

socketio = SocketIO(app)
scheduler = BackgroundScheduler()

# Configurações do banco de dados MySQL
# Configuração de conexão com o MySQL
conn = mysql.connector.connect{
    'user': 'root',
    'password': 'SqUKYLxsBrevFZapNANHFxHcIDzSAfWi',
    'host': 'monorail.proxy.rlwy.net',
    'port': '3306',
    'database': 'railway'
}
def get_db_connection():
    try:
        conn = mysql.connector.connect(**conn)  # Usando 'config' diretamente
        if conn.is_connected():
            return conn
        else:
            flash("Falha ao conectar ao banco de dados.", 'error')
            return None
    except Error as e:
        flash(f"Erro na conexão com o banco de dados: {str(e)}", 'error')
        return None

# Inicializando o Flask-login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, name, email, password):
        self.id = id
        self.name = name
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return User(**user_data)
    return None

def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_products():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM produtos')
    products = cursor.fetchall()
    conn.close()
    return products

def get_deliveries():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM deliveries')
    deliveries = cursor.fetchall()
    conn.close()
    return deliveries

@app.route('/', methods=['POST', 'GET'])
def home():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    products = get_products()
    produto_mais_caro = max(products, key=lambda x: x['preco'], default=None)
    produto_mais_barato = min(products, key=lambda x: x['preco'], default=None)
    produto_maior_quantidade = max(products, key=lambda x: x['quantidade'], default=None)
    produto_menor_quantidade = min(products, key=lambda x: x['quantidade'], default=None)

    user_name = current_user.name if current_user.is_authenticated else None
    return render_template('home.html',
                           user_name=user_name,
                           produto_mais_caro=produto_mais_caro,
                           produto_mais_barato=produto_mais_barato,
                           produto_maior_quantidade=produto_maior_quantidade,
                           produto_menor_quantidade=produto_menor_quantidade)

def is_valid_email(email):
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None

def domain_exists(domain):
    try:
        dns.resolver.resolve(domain, 'MX')
        return True
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return False

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        pwd = request.form.get('password')
        
        if not name or not email or not pwd:
            flash("Todos os campos são obrigatórios!")
            return redirect(url_for('register'))
        
        if not is_valid_email(email):
            flash("Formato de e-mail inválido")
            return redirect(url_for('register'))
        
        domain = email.split('@')[-1]
        if not domain_exists(domain):
            flash("Domínio do e-mail não encontrado")
            return redirect(url_for('register'))
        
        if get_user_by_email(email):
            flash("Email já existe")
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(pwd)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (name, email, password) VALUES (%s, %s, %s)', (name, email, hashed_password))
        conn.commit()
        conn.close()
        
        flash("Usuário registrado com sucesso")
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        user_data = get_user_by_email(email)
        
        if user_data and check_password_hash(user_data['password'], pwd):
            user = User(**user_data)
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash("Email ou senha inválidos")
            return redirect(url_for('login'))
    return render_template('login.html')

def enviar_email(destinatario, assunto, conteudo):
    chave_api = os.getenv('MAILJET_API_KEY')
    segredo_api = os.getenv('MAILJET_API_SECRET') 

    if not chave_api or not segredo_api:
        raise ValueError("Chave da API ou segredo da API não configurados")

    mailjet = Client(auth=(chave_api, segredo_api), version='v3.1')
    dados = {
        'Messages': [
            {
                'From': {
                    'Email': 'matheusfagomes86@gmail.com',
                    'Name': 'Matheus'
                },
                'To': [
                    {
                        'Email': destinatario,
                        'Name': 'Nome do Destinatário'
                    }
                ],
                'Subject': assunto,
                'TextPart': conteudo
            }
        ]
    }

    try:
        resultado = mailjet.send.create(data=dados)
        if resultado.status_code == 200:
            print(f"E-mail enviado para: {destinatario}")
        else:
            print(f"Falha ao enviar e-mail: {resultado.json()}")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

@app.route('/esqueceu-senha', methods=['GET', 'POST'])
def esqueceu_senha():
    if request.method == 'POST':
        email = request.form.get('email')
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM User WHERE email = %s', (email,))
            usuario = cursor.fetchone()

            if usuario:
                token = str(uuid.uuid4())
                cursor.execute('UPDATE User SET password_reset_token = %s WHERE email = %s', (token, email))
                conn.commit()

                link_recuperacao = url_for('redefinir_senha', token=token, _external=True)
                assunto = 'Redefinir Senha'
                conteudo = f'Clique no link para redefinir sua senha: {link_recuperacao}'
                enviar_email(email, assunto, conteudo)

            cursor.close()
            conn.close()
        
        return render_template('confirmacao_envio.html')

    return render_template('esqueceu_senha.html')

@app.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM User WHERE password_reset_token = %s', (token,))
        user = cursor.fetchone()

        if not user:
            flash('Token de redefinição inválido.', 'error')
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            nova_senha = request.form['nova_senha']
            confirmar_senha = request.form['confirmar_senha']
            
            if nova_senha != confirmar_senha:
                flash('As senhas não coincidem. Tente novamente.', 'error')
                return render_template('redefinir_senha.html', token=token)
            
            senha_hash = generate_password_hash(nova_senha, method='sha256')
            cursor.execute('UPDATE User SET senha = %s, password_reset_token = NULL WHERE password_reset_token = %s', (senha_hash, token))
            conn.commit()
            
            flash('Senha redefinida com sucesso!', 'success')
            return redirect(url_for('login'))
        
        cursor.close()
        conn.close()

    return render_template('redefinir_senha.html', token=token)
@app.route('/produto', methods=['POST', 'GET'])
@login_required
def produto():
    if request.method == 'POST':
        cod_produto = int(request.form.get('cod_produto'))

        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM produtos WHERE cod_produto = %s', (cod_produto,))
            existing_product = cursor.fetchone()

            if existing_product:
                flash('Já existe um produto com este código.')
                return redirect(url_for('produto'))

            # Inserir novo produto
            cursor.execute('INSERT INTO produtos (name, preco, quantidade, descricao, categoria, cod_produto, marca_produto) VALUES (%s, %s, %s, %s, %s, %s, %s)', 
                           (request.form.get('name'), float(request.form.get('preco')), float(request.form.get('quantidade')), 
                            request.form.get('descricao'), request.form.get('categoria'), cod_produto, request.form.get('marca_produto')))
            conn.commit()

            flash('Produto cadastrado com sucesso!')
            return redirect(url_for('produto'))
    
    return render_template('produtos.html')

@app.route('/estoque', methods=['POST', 'GET'])
@login_required
def estoque():
    return render_template('estoque.html', produtos=get_products())

@app.route('/metricas_financeiras', methods=['GET'])
@login_required
def metricas_financeiras():
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute('''
            SELECT SUM(d.quantity * p.preco) AS receita_total
            FROM deliveries d
            JOIN produtos p ON d.product_id = p.id
        ''')
        receita_total = cursor.fetchone()['receita_total'] or 0

        cursor.execute('SELECT SUM(preco * quantidade) AS custos_totais FROM produtos')
        custos_totais = cursor.fetchone()['custos_totais'] or 0

    lucro_bruto = receita_total - custos_totais
    lucro_liquido = lucro_bruto - 1000  # Defina despesas operacionais fixas

    return jsonify({
        'receita_total': receita_total,
        'custos_totais': custos_totais,
        'lucro_bruto': lucro_bruto,
        'lucro_liquido': lucro_liquido
    })

@app.route('/buscar_produto', methods=['POST'])
def buscar_produto():
    query = 'SELECT * FROM produtos WHERE 1=1'
    params = []

    for field, value in {
        'cod_produto': request.form.get('cod_produto'),
        'name': request.form.get('name'),
        'marca_produto': request.form.get('marca_produto'),
        'preco_min': request.form.get('preco_min'),
        'preco_max': request.form.get('preco_max')
    }.items():
        if value:
            query += f' AND {field} = %s'
            params.append(value)

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        produtos = cursor.fetchall()

    return render_template('produtos.html', produtos=produtos)

@app.route('/atualizar_produto', methods=['POST'])
@login_required
def atualizar_produto():
    cod_produto = request.form.get('cod_produto')
    quantidade_adicional = float(request.form.get('quantidade_adicional'))

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Product WHERE cod_produto = %s", (cod_produto,))
        produto = cursor.fetchone()

        if produto:
            nova_quantidade = produto['quantidade'] + quantidade_adicional
            cursor.execute("UPDATE Product SET quantidade = %s WHERE cod_produto = %s", (nova_quantidade, cod_produto))
            conn.commit()
            flash('Quantidade do produto atualizada com sucesso!')
        else:
            flash('Produto não encontrado.')

    return redirect(url_for('estoque'))

@app.route('/update_status', methods=['POST'])
def update_status():
    data = request.json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Delivery SET status = %s WHERE id = %s", (data.get('status'), data.get('id')))
        conn.commit()

        if cursor.rowcount > 0:
            return jsonify({'status': 'success', 'message': 'Status atualizado com sucesso!'})
        else:
            return jsonify({'status': 'error', 'message': 'Entrega não encontrada!'})

@socketio.on('connect')
def handle_connect():
    emit('status_update', {'data': 'Connected'})

@socketio.on('request_status')
def handle_request_status():
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Delivery")
        emit('status_update', {'deliveries': cursor.fetchall()})

@app.route('/send_product', methods=['POST'])
@login_required
def send_product():
    data = {
        'location_name': request.form.get('name'),
        'location_lat': float(request.form.get('lat')),
        'location_lng': float(request.form.get('lng')),
        'product_id': int(request.form.get('produto')),
        'quantity': float(request.form.get('quantidade'))
    }

    if all(data.values()):
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Product WHERE id = %s", (data['product_id'],))
            product = cursor.fetchone()

            if product and product['quantidade'] >= data['quantity']:
                cursor.execute("INSERT INTO Delivery (product_id, location_name, location_lat, location_lng, quantity, status, delivery_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                               (data['product_id'], data['location_name'], data['location_lat'], data['location_lng'], data['quantity'], 'Saiu para entrega', datetime.now()))
                cursor.execute("UPDATE Product SET quantidade = %s WHERE id = %s", (product['quantidade'] - data['quantity'], data['product_id']))
                conn.commit()

                flash(f'Produto {product["name"]} enviado para {data["location_name"]} com sucesso!', 'success')
            else:
                flash('Quantidade selecionada não está disponível em estoque.', 'error')
    else:
        flash('Dados incompletos enviados.', 'error')

    return redirect(url_for('local_entrega'))

@app.route('/validate_address', methods=['POST'])
def validate_address():
    response = requests.get(GEOCODE_URL, params={
        'latlng': f'{request.form.get("location_lat")},{request.form.get("location_lng")}',
        'key': GOOGLE_MAPS_API_KEY
    })

    result = response.json()
    if result['status'] == 'OK':
        return jsonify({'status': 'success', 'address': result['results'][0]['formatted_address']})
    else:
        return jsonify({'status': 'error', 'message': 'Endereço não válido'})

@app.route('/local_entrega_pesquisa', methods=['GET'])
@login_required
def local_entrega_pesquisa():
    search_query = request.args.get('search_query', '').strip()
    query = """
        SELECT Delivery.*, Product.name AS product_name 
        FROM Delivery 
        JOIN Product ON Delivery.product_id = Product.id
    """
    if search_query:
        query += " WHERE Delivery.location_name LIKE %s"

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, (f'%{search_query}%',) if search_query else None)
        deliveries = cursor.fetchall()

    return render_template('local_entrega_pesquisa.html', deliveries=deliveries)

@app.route('/delete_product', methods=['POST'])
@login_required
def delete_product():
    cod_produto = request.form.get('cod_produto')

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Product WHERE cod_produto = %s", (cod_produto,))
        produto = cursor.fetchone()

        if produto:
            try:
                cursor.execute("DELETE FROM Product WHERE cod_produto = %s", (cod_produto,))
                conn.commit()
                flash(f'Produto {produto["name"]} deletado com sucesso.', 'success')
                print(f'Produto {produto["name"]} deletado com sucesso.', 'success')
            except Exception as e:
                conn.rollback()
                flash(f'Erro ao deletar produto: {str(e)}', 'error')
                print(f'Erro ao deletar produto: {str(e)}', 'error')
        else:
            flash(f'Produto com código {cod_produto} não encontrado.', 'error')
            print(f'Produto com código {cod_produto} não encontrado.', 'error')

        cursor.close()
        conn.close()

    return redirect(url_for('estoque'))

@app.route('/vendas', methods=['POST', 'GET'])
@login_required
def vendas():
    return render_template('vendas.html')

@app.route('/suporte', methods=['POST', 'GET'])
@login_required
def suporte():
    return render_template('suporte.html')

@app.route('/get_delivery_locations', methods=['GET'])
def get_delivery_locations():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Delivery")
        deliveries = cursor.fetchall()
        cursor.close()
        conn.close()

        delivery_counts = {}
        for delivery in deliveries:
            if delivery['location_name'] in delivery_counts:
                delivery_counts[delivery['location_name']] += delivery['quantity']
            else:
                delivery_counts[delivery['location_name']] = delivery['quantity']

        total_deliveries = sum(delivery_counts.values())
        if total_deliveries == 0:
            percentages = {location: 0 for location in delivery_counts.keys()}
        else:
            percentages = {location: (quantity / total_deliveries) * 100 for location, quantity in delivery_counts.items()}

        return jsonify({
            'labels': list(percentages.keys()),
            'percentages': list(percentages.values())
        })

    return jsonify({
        'labels': [],
        'percentages': []
    })

def check_deliveries():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Delivery WHERE status = 'Saiu para entrega'")
        deliveries = cursor.fetchall()

        for delivery in deliveries:
            time_diff = datetime.now() - delivery['delivery_date']
            if time_diff.total_seconds() > 3600:
                cursor.execute("UPDATE Delivery SET status = %s WHERE id = %s", ('Entregue', delivery['id']))
                conn.commit()

        cursor.close()
        conn.close()

scheduler.add_job(check_deliveries, 'interval', minutes=1)
scheduler.start()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
