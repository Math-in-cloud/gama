#importações de blibliotecas
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import re
import dns.resolver
from apscheduler.schedulers.background import BackgroundScheduler
from flask_socketio import SocketIO, emit
import random
import requests


app = Flask(__name__) #Informando ao flask para procurar arquivos como templates, arquivos estáticos..


GOOGLE_MAPS_API_KEY = 'AIzaSyCFg28W1NRnx48tyCEGVQpmPmVxOBoxOtQ'
GEOCODE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'
#configura a aplicação para interagir com banco de dados e fazer a segurança do mesmo.
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.sqlite3"
app.config['SECRET_KEY'] = "random_string"
#Configurações do flask_mail
app.config['MAIL_SERVER']='smtp.example.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'your-email@example.com'
app.config['MAIL_PASSWORD'] = 'your-password'
mail = Mail(app)

socketio = SocketIO(app)
scheduler = BackgroundScheduler()
socketio = SocketIO(app)
#Inicializando o SQLAlchemy para a aplicação
db = SQLAlchemy(app)
#Iniciando o Flask-login para a aplicação
login_manager = LoginManager(app)
#Definindo a rota utilizada quando o usuário não estiver logado
login_manager.login_view = 'login'

#carregando um usuário com base no id armazenado
@login_manager.user_loader
def get_user(user_id):
    return User.query.get(int(user_id))

#criação da classe user, e criação do banco de dados do mesmo.
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    name = db.Column(db.String(86), nullable=False)
    email = db.Column(db.String(84), nullable=False, unique=True)
    password = db.Column(db.String(128), nullable=False)

    def __init__(self, name, email, password):
        self.name = name
        self.email = email
        self.set_password(password)
    #define a senha do usuário com mais segurança e cria uma criptografia para ela 
    def set_password(self, password):
        self.password = generate_password_hash(password)
    #Verifica se a senha armazenada do set_passaword e = a senha inserida
    def check_password(self, pwd):
        return check_password_hash(self.password, pwd)
    #Retornará true caso o usuário estiver ativo
    def is_active(self):
        return True
    #Retorna True se o usuário estiver ativo
    def is_authenticated(self):
        return True
    #coleta o id do usuário 
    def get_id(self):
        return str(self.id)
#Criação do Banco de dados Product, e configurações das variaveis do mesmo.
class Product(db.Model):
    __tablename__ = 'produtos'
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    name = db.Column(db.String(86))
    preco = db.Column(db.Float)
    quantidade = db.Column(db.Float)
    descricao = db.Column(db.String(86))
    categoria = db.Column(db.String(86))
    cod_produto = db.Column(db.Integer, unique=True)
    marca_produto = db.Column(db.String)

    def __init__(self, name, preco, quantidade, descricao, categoria, cod_produto, marca_produto):
        self.name = name
        self.preco = preco
        self.quantidade = quantidade
        self.descricao = descricao
        self.categoria = categoria
        self.cod_produto = cod_produto
        self.marca_produto = marca_produto
#Criação do banco de dados Delivery, e configurações das variáveis do mesmo.
class Delivery(db.Model):
    __tablename__ = 'deliveries'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'))
    location_name = db.Column(db.String(128))
    location_lat = db.Column(db.Float)
    location_lng = db.Column(db.Float)
    quantity = db.Column(db.Float)
    delivery_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String)

    #Criando uma relação entre o banco de dados dos produtos e deliveries.
    product = db.relationship('Product', backref='deliveries')

    def __init__(self, product_id, location_name, location_lat, location_lng, quantity,status,delivery_date):
        self.product_id = product_id
        self.location_name = location_name
        self.location_lat = location_lat
        self.location_lng = location_lng
        self.quantity = quantity
        self.status = status
        self.delivery_date = delivery_date


    def total_delivery_value(self):
        return self.product.preco * self.quantity  #Valor total da entrega
    
    def to_dict(self):
        return {
            'id': self.id,
            'location_name': self.location_name,
            'location_lat': self.location_lat,
            'location_lng': self.location_lng,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'status': self.status,
            'delivery_date': self.delivery_date.isoformat() if self.delivery_date else None
        }
    
    def update_delivery_status():
        deliveries = Delivery.query.all()
        for delivery in deliveries:
        # Lógica para atualizar o status
            delivery.status = random.choice(['Saiu para entrega', 'Em trânsito', 'Passou em cidade 1', 'Entregue'])
        db.session.commit()
        socketio.emit('status_update', {'deliveries': [delivery.to_dict() for delivery in deliveries]})

    scheduler.add_job(update_delivery_status, 'interval', minutes=30)  # Atualiza a cada 30 minutos
    scheduler.start()
    
#inicialização da rota Home (Principal)
@app.route('/', methods=['POST', 'GET'])
def home():
    #Se o usuário não estiver autenticado retorna para rota de login
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    #Inicializa a variável do usuário como none
    user_name = None
    #Fazendo uma pesquisa nos bancos de dados para coletar dados do produtos mais caro e mais barato e com maior e menor quantidade
    produto_mais_caro = Product.query.order_by(Product.preco.desc()).first()
    produto_mais_barato = Product.query.order_by(Product.preco).first()
    produto_maior_quantidade = Product.query.order_by(Product.quantidade.desc()).first()
    produto_menor_quantidade = Product.query.order_by(Product.quantidade).first()
    #Se o usuário estiver autenticado, o software atualiza o valor da variável user_name com o nome do usuário inserido
    if current_user.is_authenticated:
        user_name = current_user.name
    #Manda os dados coletados para o template home.hmtl.
    return render_template('home.html',
                           user_name=user_name,
                           produto_mais_caro=produto_mais_caro,
                           produto_mais_barato=produto_mais_barato,
                           produto_maior_quantidade=produto_maior_quantidade,
                           produto_menor_quantidade=produto_menor_quantidade)

def is_valid_email(email):
    # Expressão regular para validar o formato do e-mail
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None
def domain_exists(domain):
    try:
        # Tenta resolver o domínio para verificar a existência de registros MX
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
        
        if User.query.filter_by(email=email).first():
            flash("Email já existe")
            return redirect(url_for('register'))
        
        new_user = User(name=name, email=email, password=pwd)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Usuário registrado com sucesso")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao registrar usuário: {str(e)}")
    
    return render_template('register.html')

#Inicialização da rota login
@app.route('/login', methods=['GET', 'POST'])
def login():
    #Se o método for = a POST ele coleta os dados de email e senha do template.
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        #Verifica se os campos foram preenchidos
        user = User.query.filter_by(email=email).first()
        #verifica se a senha está correta        
        if user and user.check_password(pwd):
            login_user(user)
            return redirect(url_for('home'))
        #se não estiver, retorna a mensagem e retorna para a rota login novamente.
        else:
            flash("Email ou senha inválidos")
            return redirect(url_for('login'))
    #renderiza o template login.html.
    return render_template('login.html')
#Inicializa a rota produto
@app.route('/produto', methods=['POST', 'GET'])
@login_required
def produto():
    #Se o método for = a POST ele coleta os dados do template produto.
    if request.method == 'POST':
        cod_produto = int(request.form.get('cod_produto'))
        
        # Verificar se já existe um produto com o mesmo código
        existing_product = Product.query.filter_by(cod_produto=cod_produto).first()
        if existing_product:
            flash('Já existe um produto com este código.')
            return redirect(url_for('produto'))

        # Se não existir, prossegue com o cadastro do novo produto
        name = request.form.get('name')
        preco = float(request.form.get('preco'))
        quantidade = float(request.form.get('quantidade'))
        categoria = request.form.get('categoria')
        descricao = request.form.get('descricao')
        marca_produto = request.form.get('marca_produto')
        #Coloca todos os dados coletados acima em uma só variável.
        novo_produto = Product(name=name, preco=preco, quantidade=quantidade, categoria=categoria,
                               descricao=descricao, marca_produto=marca_produto, cod_produto=cod_produto)
        try:
            #adiciona os dados coletados no banco de dados.
            db.session.add(novo_produto)
            db.session.commit()
            flash('Produto cadastrado com sucesso!')
            print('Produto cadastrado com sucesso!')
            #redireciona para a rota protudo
            return redirect(url_for('produto'))
        #Casod de algum erro no cadastro, virá para esse bloco
        except Exception as e:
            #Reverte as alterações não confirmadas.
            db.session.rollback()
            print(f'Erro ao cadastrar produto: {str(e)}')
            flash(f'Erro ao cadastrar produto: {str(e)}')
    #Retorna o template dos produtos 
    return render_template('produtos.html')

#Inicialização da rota estoque
@app.route('/estoque', methods=['POST', 'GET'])
@login_required
def estoque():
    #coleta todos os dados do produto
    produto_nome = session.get('produto_nome')
    produto_quantidade = session.get('produto_quantidade')
    produto_categoria = session.get('produto_categoria')
    produto_preco = session.get('produto_preco')
    produto_descricao = session.get('produto_descricao')
    produto_marca = session.get('produto_marca')
    produto_cod = session.get('produto_cod')
    #Retorna todos os dados dos produtos para o template estoque.html.
    return render_template('estoque.html', produto_nome=produto_nome, produto_categoria=produto_categoria,
                           produto_descricao=produto_descricao, produto_marca=produto_marca,
                           produto_preco=produto_preco, produto_cod=produto_cod, produto_quantidade=produto_quantidade)
#Incialização da rota de metricas financeiras
@app.route('/metricas_financeiras', methods=['GET'])
@login_required
def metricas_financeiras():
    # Calculando Receita Total de acordo com o calculo (quantidade x produto)
    receita_total = db.session.query(
        db.func.sum(Delivery.quantity * Product.preco)
    ).join(Product, Delivery.product_id == Product.id).scalar() or 0

    # Calculando Custos Totais com base na quantidade em estoque e preço
    produtos_em_estoque = db.session.query(Product).all()
    custos_totais = sum(produto.preco * produto.quantidade for produto in produtos_em_estoque)

    # Calculando Lucro Bruto
    lucro_bruto = receita_total - custos_totais

    # Calculando Despesas Operacionais (exemplo)
    despesas_operacionais = 1000  # Defina um valor fixo ou consulte uma tabela de despesas operacionais

    # Calculando Lucro Líquido
    lucro_liquido = lucro_bruto - despesas_operacionais
    #Retornar os dados 
    return jsonify({
        'receita_total': receita_total,
        'custos_totais': custos_totais,
        'lucro_bruto': lucro_bruto,
        'lucro_liquido': lucro_liquido
    })
#Inicializa a rota busca produto
@app.route('/buscar_produto', methods=['POST'])
def buscar_produto():
    #Coleta os dados abaixo
    cod_produto = request.form.get('cod_produto')
    name = request.form.get('name')
    marca_produto = request.form.get('marca_produto')
    preco_min = request.form.get('preco_min')
    preco_max = request.form.get('preco_max')
    #Busca o produto no banco de dados.
    query = Product.query
    #verifica se o codigo for fornecido, e se foi fornecido adiciona o filtro de busca pelo código.
    if cod_produto:
        query = query.filter(Product.cod_produto == cod_produto)
    #Verifica se o nome foi inserido, e se foi inserido adiciona o filtro de busca pelo nome.
    if name:
        query = query.filter(Product.name.ilike(f"%{name}%"))
    #Verifica se a marca foi inserida, e se foi inserida adiciona o filtro de busca pela marca.
    if marca_produto:
        query = query.filter(Product.marca_produto.ilike(f"%{marca_produto}%"))
    #Adiciona um filtro de busca para preço minimo.
    if preco_min:
        query = query.filter(Product.preco >= preco_min)
    #Adiciona um filtro de busca para preço maximo.
    if preco_max:
        query = query.filter(Product.preco <= preco_max)
    #Retorna os produtos encontrados
    produtos = query.all()
    #Retornar os dados para o template estoque.html.
    return render_template('estoque.html', produtos=produtos)

#Incializa a rota atualizar produto.
@app.route('/atualizar_produto', methods=['POST'])
@login_required
def atualizar_produto():
    #Coleta os dados abaixo.
    cod_produto = request.form.get('cod_produto')
    quantidade_adicional = float(request.form.get('quantidade_adicional'))
    #Busca o produto no banco de dados.
    produto = Product.query.filter_by(cod_produto=cod_produto).first()
    #Verifica se o produto foi encontrado.
    if produto:
        #Atualiza a quantidade do produto.
        produto.quantidade += quantidade_adicional
        db.session.commit()
        flash('Quantidade do produto atualizada com sucesso!')
    else:
        flash('Produto não encontrado.')
    #Redireciona para a rota estoque.
    return redirect(url_for('estoque'))

@app.route('/update_status', methods=['POST'])
def update_status():
    data = request.json
    delivery_id = data.get('id')
    status = data.get('status')

    delivery = Delivery.query.get(delivery_id)
    if delivery:
        delivery.status = status
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Status atualizado com sucesso!'})
    return jsonify({'status': 'error', 'message': 'Entrega não encontrada!'})

@socketio.on('connect')
def handle_connect():
    emit('status_update', {'data': 'Connected'})

@socketio.on('request_status')
def handle_request_status():
    deliveries = Delivery.query.all()
    emit('status_update', {'deliveries': [delivery.to_dict() for delivery in deliveries]})
#Inicializa a rota send produtct
@app.route('/send_product', methods=['POST'])
@login_required
def send_product():
    # Coleta de dados
    location_name = request.form.get('name')
    location_lat = request.form.get('lat')
    location_lng = request.form.get('lng')
    product_id = request.form.get('produto')
    quantity = request.form.get('quantidade')
    
    # Mensagens de depuração
    print(f'Recebido - Nome: {location_name}, Latitude: {location_lat}, Longitude: {location_lng}, Produto ID: {product_id}, Quantidade: {quantity}')
    
    # Verifica se todos os dados necessários foram fornecidos
    if location_name and location_lat and location_lng and product_id and quantity:
        try:
            location_lat = float(location_lat)
            location_lng = float(location_lng)
            product_id = int(product_id)
            quantity = float(quantity)
            
            # Busca o produto no banco de dados pelo ID
            product = Product.query.get(product_id)
            
            # Verifica se o produto foi encontrado e se a quantidade está disponível
            if product and product.quantidade >= quantity:
                # Cria uma nova entrega
                new_delivery = Delivery(
                    product_id=product_id,
                    location_name=location_name,
                    location_lat=location_lat,
                    location_lng=location_lng,
                    quantity=quantity,
                    status='Saiu para entrega',
                    delivery_date=datetime.now()
                )
                
                # Atualiza a quantidade do produto em estoque
                product.quantidade -= quantity
                
                # Adiciona e comita as mudanças
                db.session.add(new_delivery)
                db.session.commit()
                
                flash(f'Produto {product.name} enviado para {location_name} com sucesso!', 'success')
                print(f'Produto {product.name} enviado para {location_name} com sucesso!')
            else:
                flash('Quantidade selecionada não está disponível em estoque.', 'error')
                print('Quantidade selecionada não está disponível em estoque.')
        except ValueError as ve:
            flash(f'Erro de conversão de dados: {str(ve)}', 'error')
            print(f'Erro de conversão de dados: {str(ve)}')
    else:
        flash('Dados incompletos enviados.', 'error')
        print('Dados incompletos enviados.')
    
    # Redireciona para a página de local de entrega
    return redirect(url_for('local_entrega'))

@app.route('/validate_address', methods=['POST'])
def validate_address():
    lat = request.form.get('location_lat')
    lng = request.form.get('location_lng')

    # Faz uma requisição para o Google Maps Geocoding API
    response = requests.get(GEOCODE_URL, params={
        'latlng': f'{lat},{lng}',
        'key': GOOGLE_MAPS_API_KEY
    })
    
    result = response.json()

    if result['status'] == 'OK':
        return jsonify({'status': 'success', 'address': result['results'][0]['formatted_address']})
    else:
        return jsonify({'status': 'error', 'message': 'Endereço não válido'})

#Incialização da rota local entrega pesquisa
@app.route('/local_entrega_pesquisa', methods=['GET'])
@login_required
def local_entrega_pesquisa():
    #Busca as entregas.
    search_query = request.args.get('search_query', '').strip()

    if search_query:
        # Utiliza o operador like para procurar por nomes semelhantes
        deliveries = db.session.query(Delivery).join(Product).filter(
            Delivery.location_name.ilike(f'%{search_query}%')
        ).all()

        # Cria uma lista com os dados das entregas, incluindo o nome do produto.
        results = []
        #Faz yma busca na tabela deliveires.
        for delivery in deliveries:
            product = Product.query.get(delivery.product_id)
            #adiciona os dados na lista de results.
            results.append({
                'location_name': delivery.location_name,
                'location_lat': delivery.location_lat,
                'location_lng': delivery.location_lng,
                'product_name': product.name if product else 'Desconhecido',
                'quantity': delivery.quantity,
                'status': delivery.status
            })

    else:
        results = []
    print(f'Deliveries found: {results}')
    #Retorna o template do local_entrega_pesquisa.html
    return render_template('local_entrega_pesquisa.html', deliveries=results)


#Inicializa a rota delete_product
@app.route('/delete_product', methods=['POST'])
@login_required
def delete_product():
    #Puxa o código do produto.
    cod_produto = request.form.get('cod_produto')
    #faz a busca do código inserido no banco de dados.
    produto = Product.query.filter_by(cod_produto=cod_produto).first()
    #Se o produto for encontrado.
    if produto:
        try:
            #Se o produto for encontrado ele e deletado do banco de dados.
            db.session.delete(produto)
            #Atualzia o banco de dados
            db.session.commit()
            flash(f'Produto {produto.name} deletado com sucesso.', 'success')
            print(f'Produto {produto.name} deletado com sucesso.', 'success')
        #Se der erro.
        except Exception as e:
            #Reverte as alterações feitas.
            db.session.rollback()
            flash(f'Erro ao deletar produto: {str(e)}', 'error')
            print(f'Erro ao deletar produto: {str(e)}', 'error')
    else:
        flash(f'Produto com código {cod_produto} não encontrado.', 'error')
        print(f'Produto com código {cod_produto} não encontrado.', 'error')
    #Redireciona para a rota estoque.
    return redirect(url_for('estoque'))
#Incializa a rota vendas
@app.route('/vendas', methods=['POST', 'GET'])
@login_required
def vendas():
    #Retorna o template vendas.html.
    return render_template('vendas.html')
#Incializa a rota suporte 
@app.route('/suporte', methods=['POST', 'GET'])
@login_required
def suporte():
    #Retorna o template vendas.html.
    return render_template('suporte.html')

#incializa a rota get_delivery_locations.
@app.route('/get_delivery_locations', methods=['GET'])
def get_delivery_locations():
    try:
        # Consulta para obter todas as entregas
        deliveries = Delivery.query.all()

        # Dicionário para armazenar os dados de entrega por local
        delivery_counts = {}

        # Contagem de entregas por local
        for delivery in deliveries:
            if delivery.location_name in delivery_counts:
                delivery_counts[delivery.location_name] += delivery.quantity
            else:
                delivery_counts[delivery.location_name] = delivery.quantity

         # Calcular o total de entregas para percentuais.
        total_deliveries = sum(delivery_counts.values())
        if total_deliveries == 0:
            total_deliveries = 1  # Para evitar divisão por zero.

        # Preparar os dados para retorno como JSON.
        locations_data = [{
            'name': location_name,
            'deliveries': delivery_counts[location_name],
            'percentage': (delivery_counts[location_name] / total_deliveries) * 100
        } for location_name in delivery_counts]

        return jsonify(locations_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
#Inicializa a rota delivery_locations_list.  
@app.route('/delivery_locations_list', methods=['GET'])
@login_required
def delivery_locations_list():
    try:
        # Consulta para obter todas as entregas.
        search_query = request.args.get('search_query', '').strip()
        #Se a entrega for encontrada
        if search_query:
            #Busca o local de entrega no banco de dados.
            deliveries = Delivery.query.filter(Delivery.location_name.ilike(f'%{search_query}%')).all()
        else:
            #Busca todas as entregas no banco de dados.
            deliveries = Delivery.query.all()
        #Inicialização da variável para contagens de todas entregas.
        delivery_counts = {}

        # Itera sobre todas as entregas e contabiliza a quantidade por local
        for delivery in deliveries:
            if delivery.location_name in delivery_counts:
                delivery_counts[delivery.location_name] += delivery.quantity
            else:
                delivery_counts[delivery.location_name] = delivery.quantity

        # Preparar os dados para retorno como uma lista de tuplas
        locations_data = [(location_name, delivery_counts[location_name]) for location_name in delivery_counts]
        print(f'Dados de locais de entrega: {locations_data}')
        #Retorna o template de produtos_Enviados.html, e envia os dados contidos na variável locations_data.
        return render_template('produtos_Enviados.html', locations_data=locations_data)
    #Caso de erro, virá para esse bloco.
    except Exception as e:
        flash(f'Erro ao carregar dados de locais de entrega: {str(e)}', 'error')
        return redirect(url_for('home'))

#incializa a rota dados_rotatividade_estoque.
@app.route('/dados_rotatividade_estoque', methods=['GET'])
@login_required
def dados_rotatividade_estoque():
    try:
        # Consulta para obter todas as entregas.
        products = Product.query.all()
        rotation_data = []
        #pesquisa a coluna produto na tabela products, e se o produto for encontrado.
        for product in products:
            #Busca a quantidade de produtos no estoque.
            total_entregue = sum(delivery.total_delivery_value() for delivery in product.deliveries)
            rotatividade = total_entregue / product.preco if product.preco != 0 else 0
            #Adiciona os dados na lista rotation_data.
            rotation_data.append({  
                'produto': product.name,
                'total_entregue': total_entregue,
                'rotatividade': rotatividade
            })

        print('Dados de rotatividade de estoque:', rotation_data)  # Verifica no terminal Flask

        return jsonify(rotation_data)
    #Bloco de erro, caso não de para buscar os dados de rotatividade de estoque.
    except Exception as e:
        print('Erro ao buscar dados de rotatividade de estoque:', str(e))
        return jsonify({'error': str(e)})

#Incialização da rota produtos_mais_vendidos.
@app.route('/produtos_mais_vendidos', methods=['GET'])
@login_required
def produtos_mais_vendidos():
    try:
        #Faz a busca de todos os produtos no banco de dados de produtos.
        products = Product.query.all()
        #Incialização da variável de top vendas.
        top_selling_products = []
        #se o produto for encotrado
        for product in products:
            total_vendido = sum(delivery.quantity for delivery in product.deliveries)
            #Adiciona os dados na lista top_selling_products.
            top_selling_products.append({
                'produto': product.name,
                'total_vendido': total_vendido,
                'preco': product.preco,
                'categoria': product.categoria
            })
        #retorna o template de produtos_mais_vendidos.hmtl juntamente com os dados contidos na variável top_selling_products.
        return render_template('produtos_mais_vendidos.html', top_selling_products=top_selling_products)
    #Bloco de erro para quando não conseguir coletar os dados corretamente.
    except Exception as e:
        flash(f'Erro ao calcular produtos mais vendidos: {str(e)}', 'error')
        return redirect(url_for('home'))

#Inicialização da rota comparacao_vendas_mensais
@app.route('/comparacao_vendas_mensais', methods=['GET'])
def comparacao_vendas_mensais():
    #Calculo dos ultimos doze meses com base na data atual, e quantidade de dias totais do ano.
    ultimos_12_meses = datetime.now() - timedelta(days=365)
    #Inicia uma nova consulta no banco de dados.
    dados_ano_atual = db.session.query(
        #Formatação da data
        db.func.strftime('%Y-%m', Delivery.delivery_date).label('mes'),
        #Calculo do total das vendas com base no calculo (quantidade x preco)
        db.func.sum(Delivery.quantity * Product.preco).label('vendas_totais')
    ).join(Product, Delivery.product_id == Product.id #Faz a junção onde o id do produto na tabela delivery e = na tabela de produtos.
    ).filter(Delivery.delivery_date >= ultimos_12_meses #Faz um filtro para incluir apenas as entregas que forem maior ou = aos ultimos 12 meses.
    ).group_by('mes').all() #Agrupa os resultados por mês.
    #Inicia uma nova consulta no banco de dados.
    dados_ano_anterior = db.session.query(
        #Formatação da data
        db.func.strftime('%Y-%m', Delivery.delivery_date - timedelta(days=365)).label('mes'),
        #Calculo do total das vendas com base no calculo (quantidade x preco)
        db.func.sum(Delivery.quantity * Product.preco).label('vendas_totais')
    ).join(Product, Delivery.product_id == Product.id #Faz a junção onde o id do produto na tabela delivery e = na tabela de produtos.
    ).filter(Delivery.delivery_date >= ultimos_12_meses - timedelta(days=365)#Faz um filtro para incluir apenas as entregas que forem maior ou = aos ultimos 12 meses.
    ).group_by('mes').all() #Agrupa os resultados por mês.

    vendas_ano_atual = {mes: vendas_totais for mes, vendas_totais in dados_ano_atual}
    vendas_ano_anterior = {mes: vendas_totais for mes, vendas_totais in dados_ano_anterior}
    #Incializa uma na lista na variável dados_resposta.
    dados_resposta = []
    #Percorre o mês e o ano atual de vendas.
    for mes in vendas_ano_atual:
        #Adiciona os dados na lista.
        dados_resposta.append({
            "mes": mes,
            "vendas_ano_atual": vendas_ano_atual.get(mes, 0),
            "vendas_ano_anterior": vendas_ano_anterior.get(mes, 0)
        })
    #Retorno de dados para o script na pagina home.
    return jsonify(dados_resposta)

#Inicializa a rota local de entrega.
@app.route('/local_entrega', methods=['POST', 'GET'])
@login_required
def local_entrega():
    #Faz uma busca no banco de dados dos produtos. 
    products = Product.query.all()
    #Retorna o template local_entrega.html juntamente com todos os dados dos produtos.
    return render_template('local_entrega.html', products=products)
#Incializa a rota de produtos_enviados.
@app.route('/produtos_enviados', methods=['POST','GET'])
@login_required
def produtos_enviados():
    #Retorna o template de produtos_Enviados.html.
    return render_template('produtos_Enviados.html')

#Inicialização da rota logout.
@app.route('/logout')
@login_required
def logout():
    #logout do usuário.
    logout_user()
    #limpa a sessão atual.
    session.clear()
    #Retorna para a rota login
    return redirect(url_for('login'))


 
if __name__ == '__main__':
    db.create_all()#Cria todos os banco de dados.
    app.run(debug=True)#Executa o app com debug ativo.
if __name__ == '__main__':
    socketio.run(app)
