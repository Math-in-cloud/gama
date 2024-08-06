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
from flask_socketio import SocketIO, emit
from mailjet_rest import Client
import requests, os, uuid
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta

app = Flask(__name__)
socketio = SocketIO(app)
scheduler = BackgroundScheduler()
scheduler.start()

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
config = {
    'user': 'root',
    'password': 'SqUKYLxsBrevFZapNANHFxHcIDzSAfWi',
    'host': 'monorail.proxy.rlwy.net',
    'port': '20439',
    'database': 'railway'
}
def get_db_connection():
    try:
        conn = mysql.connector.connect(**config)
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
    def __init__(self, id, name, email, password, password_reset_token=None):
        self.id = id
        self.name = name
        self.email = email
        self.password = password
        self.password_reset_token = password_reset_token
        
@login_manager.user_loader
def load_user(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, email, password FROM users WHERE id = %s', (user_id,))
        user_data = cursor.fetchone()
    return User(
        id=user_data['id'],
        name=user_data['name'],
        email=user_data['email'],
        password=user_data['password']
    ) if user_data else None
def get_user_by_email(email):
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, email, password FROM users WHERE email = %s', (email,))
        return cursor.fetchone()

def get_products():
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM Product')
        return cursor.fetchall()

def get_deliveries():
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM deliveries')
        return cursor.fetchall()

# Rotas da aplicação
@app.route('/', methods=['POST', 'GET'])
def home():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    products = get_products()
    produto_mais_caro = max(products, key=lambda x: x['preco'], default=None)
    produto_mais_barato = min(products, key=lambda x: x['preco'], default=None)
    produto_maior_quantidade = max(products, key=lambda x: x['quantidade'], default=None)
    produto_menor_quantidade = min(products, key=lambda x: x['quantidade'], default=None)

    return render_template('home.html',
                           user_name=current_user.name,
                           produto_mais_caro=produto_mais_caro,
                           produto_mais_barato=produto_mais_barato,
                           produto_maior_quantidade=produto_maior_quantidade,
                           produto_menor_quantidade=produto_menor_quantidade)

def is_valid_email(email):
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None

def domain_exists(domain):
    try:
        dns.resolver.resolve(domain, 'MX')
        return True
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return False

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name, email, pwd = request.form.get('name'), request.form.get('email'), request.form.get('password')
        
        if not all([name, email, pwd]):
            flash("Todos os campos são obrigatórios!")
            return redirect(url_for('register'))
        
        if not is_valid_email(email):
            flash("Formato de e-mail inválido")
            return redirect(url_for('register'))
        
        if not domain_exists(email.split('@')[-1]):
            flash("Domínio do e-mail não encontrado")
            return redirect(url_for('register'))
        
        if get_user_by_email(email):
            flash("Email já existe")
            return redirect(url_for('register'))
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (name, email, password) VALUES (%s, %s, %s)', 
                           (name, email, generate_password_hash(pwd)))
            conn.commit()
        
        flash("Usuário registrado com sucesso")
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email, pwd = request.form.get('email'), request.form.get('password')
        user_data = get_user_by_email(email)
        
        if user_data and check_password_hash(user_data['password'], pwd):
            login_user(User(**user_data))
            return redirect(url_for('home'))
        else:
            flash("Email ou senha inválidos")
            return redirect(url_for('login'))
    return render_template('login.html')

def enviar_email(destinatario, assunto, conteudo):
    mailjet = Client(auth=(os.getenv('MAILJET_API_KEY'), os.getenv('MAILJET_API_SECRET')), version='v3.1')
    dados = {
        'Messages': [
            {
                'From': {'Email': 'matheusfagomes86@gmail.com', 'Name': 'Matheus'},
                'To': [{'Email': destinatario, 'Name': 'Nome do Destinatário'}],
                'Subject': assunto,
                'TextPart': conteudo
            }
        ]
    }
    resultado = mailjet.send.create(data=dados)
    if resultado.status_code != 200:
        print(f"Falha ao enviar e-mail: {resultado.json()}")

@app.route('/esqueceu-senha', methods=['GET', 'POST'])
def esqueceu_senha():
    if request.method == 'POST':
        email = request.form.get('email')
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            usuario = cursor.fetchone()

            if usuario:
                token = str(uuid.uuid4())
                cursor.execute('UPDATE users SET password_reset_token = %s WHERE email = %s', (token, email))
                conn.commit()
                link_recuperacao = url_for('redefinir_senha', token=token, _external=True)
                enviar_email(email, 'Redefinir Senha', f'Clique no link para redefinir sua senha: {link_recuperacao}')

        return render_template('confirmacao_envio.html')

    return render_template('esqueceu_senha.html')

@app.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users WHERE password_reset_token = %s', (token,))
        user = cursor.fetchone()

        if not user:
            flash('Token de redefinição inválido.', 'error')
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            nova_senha = request.form['nova_senha']
            confirmar_senha = request.form['confirmar_senha']
            
            if nova_senha != confirmar_senha:
                flash('As senhas não coincidem. Tente novamente.') 
@app.route('/produto', methods=['POST', 'GET'])
@login_required
def produto():
    if request.method == 'POST':
        cod_produto = int(request.form.get('cod_produto'))
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM Product WHERE cod_produto = %s', (cod_produto,))
        existing_product = cursor.fetchone()
        conn.close()

        if existing_product:
            flash('Já existe um produto com este código.')
            return redirect(url_for('produto'))

        name = request.form.get('name')
        preco = float(request.form.get('preco'))
        quantidade = float(request.form.get('quantidade'))
        categoria = request.form.get('categoria')
        descricao = request.form.get('descricao')
        marca_produto = request.form.get('marca_produto')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO Product (name, preco, quantidade, descricao, categoria, cod_produto, marca_produto) VALUES (%s, %s, %s, %s, %s, %s, %s)', 
                       (name, preco, quantidade, descricao, categoria, cod_produto, marca_produto))
        conn.commit()
        conn.close()

        flash('Produto cadastrado com sucesso!')
        return redirect(url_for('produto'))
    
    return render_template('produtos.html')

@app.route('/estoque', methods=['POST', 'GET'])
@login_required
def estoque():
    products = get_products()
    return render_template('estoque.html', products=products)

@app.route('/metricas_financeiras', methods=['GET'])
@login_required
def metricas_financeiras():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute('''
        SELECT SUM(d.quantity * p.preco) AS receita_total
        FROM deliveries d
        JOIN Product p ON d.Product_id = p.id
    ''')
    receita_total = cursor.fetchone()['receita_total'] or 0

    cursor.execute('SELECT SUM(preco * quantidade) AS custos_totais FROM Product')
    custos_totais = cursor.fetchone()['custos_totais'] or 0

    lucro_bruto = receita_total - custos_totais
    despesas_operacionais = 1000  # Defina um valor fixo ou consulte uma tabela de despesas operacionais
    lucro_liquido = lucro_bruto - despesas_operacionais

    conn.close()

    return jsonify({
        'receita_total': receita_total,
        'custos_totais': custos_totais,
        'lucro_bruto': lucro_bruto,
        'lucro_liquido': lucro_liquido
    })

@app.route('/buscar_produto', methods=['POST'])
def buscar_produto():
    cod_produto = request.form.get('cod_produto')
    name = request.form.get('name')
    marca_produto = request.form.get('marca_produto')
    preco_min = request.form.get('preco_min')
    preco_max = request.form.get('preco_max')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = 'SELECT * FROM Product WHERE 1=1'
    params = []

    if cod_produto:
        query += ' AND cod_produto = %s'
        params.append(cod_produto)
    if name:
        query += ' AND name LIKE %s'
        params.append(f'%{name}%')
    if marca_produto:
        query += ' AND marca_produto LIKE %s'
        params.append(f'%{marca_produto}%')
    if preco_min:
        query += ' AND preco >= %s'
        params.append(preco_min)
    if preco_max:
        query += ' AND preco <= %s'
        params.append(preco_max)

    cursor.execute(query, params)
    produtos = cursor.fetchall()
    conn.close()

    return render_template('produtos.html', produtos=produtos)
# Inicializa a rota atualizar produto
@app.route('/atualizar_produto', methods=['POST'])
@login_required
def atualizar_produto():
    cod_produto = request.form.get('cod_produto')
    quantidade_adicional = float(request.form.get('quantidade_adicional'))

    conn = get_db_connection()
    if conn:
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

        cursor.close()
        conn.close()
    
    return redirect(url_for('estoque'))

@app.route('/update_status', methods=['POST'])
def update_status():
    data = request.json
    deliveries_id = data.get('id')
    status = data.get('status')

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE deliveries SET status = %s WHERE id = %s", (status, deliveries_id))
        conn.commit()

        if cursor.rowcount > 0:
            response = jsonify({'status': 'success', 'message': 'Status atualizado com sucesso!'})
        else:
            response = jsonify({'status': 'error', 'message': 'Entrega não encontrada!'})

        cursor.close()
        conn.close()

        return response

@socketio.on('connect')
def handle_connect():
    emit('status_update', {'data': 'Connected'})

@socketio.on('request_status')
def handle_request_status():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM deliveries")
        deliveries = cursor.fetchall()

        emit('status_update', {'deliveries': deliveries})

        cursor.close()
        conn.close()

# Inicializa a rota send_product
@app.route('/send_product', methods=['POST'])
@login_required
def send_product():
    location_name = request.form.get('name')
    location_lat = request.form.get('lat')
    location_lng = request.form.get('lng')
    product_id = request.form.get('produto')
    quantity = request.form.get('quantidade')

    print(f'Recebido - Nome: {location_name}, Latitude: {location_lat}, Longitude: {location_lng}, Produto ID: {product_id}, Quantidade: {quantity}')

    if location_name and location_lat and location_lng and product_id and quantity:
        try:
            location_lat = float(location_lat)
            location_lng = float(location_lng)
            product_id = int(product_id)
            quantity = float(quantity)

            conn = get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM Product WHERE id = %s", (product_id,))
                product = cursor.fetchone()

                if product and product['quantidade'] >= quantity:
                    cursor.execute("INSERT INTO deliveries (product_id, location_name, location_lat, location_lng, quantity, status, delivery_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                   (product_id, location_name, location_lat, location_lng, quantity, 'Saiu para entrega', datetime.now()))
                    cursor.execute("UPDATE Product SET quantidade = %s WHERE id = %s", (product['quantidade'] - quantity, product_id))
                    conn.commit()

                    flash(f'Produto {product["name"]} enviado para {location_name} com sucesso!', 'success')
                    print(f'Produto {product["name"]} enviado para {location_name} com sucesso!')
                else:
                    flash('Quantidade selecionada não está disponível em estoque.', 'error')
                    print('Quantidade selecionada não está disponível em estoque.')

                cursor.close()
                conn.close()

        except ValueError as ve:
            flash(f'Erro de conversão de dados: {str(ve)}', 'error')
            print(f'Erro de conversão de dados: {str(ve)}')
    else:
        flash('Dados incompletos enviados.', 'error')
        print('Dados incompletos enviados.')

    return redirect(url_for('local_entrega'))

@app.route('/validate_address', methods=['POST'])
def validate_address():
    lat = request.form.get('location_lat')
    lng = request.form.get('location_lng')

    response = requests.get(GEOCODE_URL, params={
        'latlng': f'{lat},{lng}',
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

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        if search_query:
            cursor.execute("SELECT deliveries.*, Product.name AS product_name FROM deliveries JOIN Product ON deliveries.Product_id = Product.id WHERE deliveries.location_name LIKE %s", (f'%{search_query}%',))
        else:
            cursor.execute("SELECT deliveries.*, Product.name AS product_name FROM deliveries JOIN Product ON deliveries.Product_id = Product.id")

        deliveries = cursor.fetchall()
        cursor.close()
        conn.close()
    else:
        deliveries = []

    print(f'Deliveries found: {deliveries}')
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


@app.route('/deliveries_locations_list', methods=['GET'])
@login_required
def deliveries_locations_list():
    try:
        search_query = request.args.get('search_query', '').strip()
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Consulta SQL para obter as entregas filtradas por local
        if search_query:
            query = """
                SELECT
                    location_name,
                    SUM(quantity) AS total_quantity
                FROM
                    deliveries
                WHERE
                    location_name LIKE %s
                GROUP BY
                    location_name
            """
            cursor.execute(query, (f'%{search_query}%',))
        else:
            query = """
                SELECT
                    location_name,
                    SUM(quantity) AS total_quantity
                FROM
                    deliveries
                GROUP BY
                    location_name
            """
            cursor.execute(query)

        deliveries = cursor.fetchall()
        conn.close()

        # Convertendo os resultados em dicionários
        deliveries_counts = {deliveries['location_name']: deliveries['total_quantity'] for deliveries in deliveries}

        return jsonify(deliveries_counts)
    
    except Exception as e:
        print(f'Erro ao buscar locais de entrega: {str(e)}')
        return jsonify({'error': str(e)})


@app.route('/get_deliveries_locations', methods=['GET'])
def get_deliveries_locations():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM deliveries")
        deliveries = cursor.fetchall()
        cursor.close()
        conn.close()

        deliveries_counts = {}
        for deliveries in deliveries:
            if deliveries['location_name'] in deliveries_counts:
                deliveries_counts[deliveries['location_name']] += deliveries['quantity']
            else:
                deliveries_counts[deliveries['location_name']] = deliveries['quantity']

        total_deliveries = sum(deliveries_counts.values())
        if total_deliveries == 0:
            percentages = {location: 0 for location in deliveries_counts.keys()}
        else:
            percentages = {location: (quantity / total_deliveries) * 100 for location, quantity in deliveries_counts.items()}

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
        cursor.execute("SELECT * FROM deliveries WHERE status = 'Saiu para entrega'")
        deliveries = cursor.fetchall()

        for deliveries in deliveries:
            time_diff = datetime.now() - deliveries['delivery_date']
            if time_diff.total_seconds() > 3600:
                cursor.execute("UPDATE deliveries SET status = %s WHERE id = %s", ('Entregue', deliveries['id']))
                conn.commit()

        cursor.close()
        conn.close()

scheduler.add_job(check_deliveries, IntervalTrigger(minutes=1), id='check_deliveries_job')
@app.route('/dados_rotatividade_estoque', methods=['GET'])
@login_required
def dados_rotatividade_estoque():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Consulta para calcular a rotatividade do estoque
        query = """
            SELECT
                p.name AS produto,
                SUM(d.quantity) AS total_entregue,
                IFNULL(SUM(d.quantity) / NULLIF(p.preco, 0), 0) AS rotatividade
            FROM
                Product p
            JOIN
                deliveries d ON p.id = d.Product_id
            GROUP BY
                p.id
            HAVING
                p.preco != 0
        """
        cursor.execute(query)
        rotation_data = cursor.fetchall()
        conn.close()

        # Retornando os dados em formato JSON
        return jsonify(rotation_data)
    
    except Exception as e:
        print('Erro ao buscar dados de rotatividade de estoque:', str(e))
        return jsonify({'error': str(e)})
@app.route('/produto_mais_vendidos', methods=['GET'])
@login_required
def produto_mais_vendidos():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Consulta para obter os Product mais vendidos
        query = """
            SELECT
                p.name AS produto,
                SUM(d.quantity) AS total_vendido,
                p.preco,
                p.categoria
            FROM
                Product p
            JOIN
                deliveries d ON p.id = d.Product_id
            GROUP BY
                p.id
            ORDER BY
                total_vendido DESC
        """
        cursor.execute(query)
        top_selling_products = cursor.fetchall()
        conn.close()

        # Retornando o template com os dados
        return render_template('produto_mais_vendidos.html', top_selling_products=top_selling_products)
    
    except Exception as e:
        flash(f'Erro ao calcular Product mais vendidos: {str(e)}', 'error')
        return redirect(url_for('home'))

@app.route('/comparacao_vendas_mensais', methods=['GET'])
def comparacao_vendas_mensais():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Calculo dos últimos doze meses
    ultimos_12_meses = datetime.now() - timedelta(days=365)

    # Dados do ano atual
    query_ano_atual = """
        SELECT
            DATE_FORMAT(delivery_date, '%Y-%m') AS mes,
            SUM(quantity * preco) AS vendas_totais
        FROM
            deliveries
        JOIN
            Product ON deliveries.Product_id = Product.id
        WHERE
            delivery_date >= %s
        GROUP BY
            mes
    """
    cursor.execute(query_ano_atual, (ultimos_12_meses,))
    dados_ano_atual = cursor.fetchall()

    # Dados do ano anterior
    query_ano_anterior = """
        SELECT
            DATE_FORMAT(delivery_date - INTERVAL 1 YEAR, '%Y-%m') AS mes,
            SUM(quantity * preco) AS vendas_totais
        FROM
            deliveries
        JOIN
            Product ON deliveries.Product_id = Product.id
        WHERE
            delivery_date >= %s - INTERVAL 1 YEAR
        GROUP BY
            mes
    """
    cursor.execute(query_ano_anterior, (ultimos_12_meses,))
    dados_ano_anterior = cursor.fetchall()

    conn.close()

    # Convertendo os resultados em dicionários
    vendas_ano_atual = {row['mes']: row['vendas_totais'] for row in dados_ano_atual}
    vendas_ano_anterior = {row['mes']: row['vendas_totais'] for row in dados_ano_anterior}

    # Preparando a resposta
    dados_resposta = []
    for mes in vendas_ano_atual:
        dados_resposta.append({
            "mes": mes,
            "vendas_ano_atual": vendas_ano_atual.get(mes, 0),
            "vendas_ano_anterior": vendas_ano_anterior.get(mes, 0)
        })

    return jsonify(dados_resposta)
@app.route('/local_entrega', methods=['POST', 'GET'])
@login_required
def local_entrega():
    try:
        # Conectar ao banco de dados MySQL
        connection = mysql.connector.connect(**config)
        
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Product")
            products = cursor.fetchall()
    
    except Error as e:
        print(f"Erro ao conectar ao MySQL: {e}")
        products = []
    
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
    
    # Retorna o template local_entrega.html juntamente com todos os dados dos produtos.
    return render_template('local_entrega.html', products=products)
#Inicialização da rota logout.
@app.route('/logout')
@login_required
def logout():
    #logout do usuário.
    #limpa a sessão atual.
    session.clear()
    #Retorna para a rota login
    return redirect(url_for('login'))

if __name__ == '__main__':
    try:
        # Inicia o servidor com SocketIO
        socketio.run(app, host='0.0.0.0', port=5000)
    except (KeyboardInterrupt, SystemExit):
        # Encerra o scheduler de forma limpa ao sair do aplicativo
        scheduler.shutdown()
