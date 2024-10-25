# import
from io import StringIO
import csv
from flask import Flask, render_template, url_for, redirect, session, request, flash, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DecimalField, FileField, SubmitField, PasswordField
from wtforms.validators import InputRequired, Length, NumberRange, ValidationError
from flask_bcrypt import Bcrypt
from datetime import datetime

app = Flask(__name__)

# configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SECRET_KEY'] = 'timofey'

# initialization
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# database tables
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    photo = db.Column(db.String(100))
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    # if user is active (because of error somewhere)
    def is_active(self):
        return True

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)  
    user = db.relationship('User', backref=db.backref('cart', uselist=False))  

class CartProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('cart.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer, nullable=False)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    order_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    delivery_address = db.Column(db.String(255))
    order_items = db.relationship('OrderItem', backref='order', lazy=True) 

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    price_at_order = db.Column(db.Numeric(10, 2), nullable=False)

# creating tables in the database (if they don't exist)
with app.app_context():
    db.create_all()

# forms for reg, log etc.
class registerForm(FlaskForm):
    first_name = StringField(validators=[InputRequired(), Length(min=2, max=50)], render_kw={"placeholder": "First Name"})
    last_name = StringField(validators=[InputRequired(), Length(min=2, max=50)], render_kw={"placeholder": "Last Name"})
    email = StringField(validators=[InputRequired(), Length(min=4, max=100)], render_kw={"placeholder": "Email"})
    password = PasswordField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Password"})
    submit = SubmitField("Register")

    def validate_email(self, email):
        existing_user_email = User.query.filter_by(email=email.data).first()
        if existing_user_email:
            raise ValidationError('That email already exists. Please choose a different one.')

class loginForm(FlaskForm):
    email = StringField(validators=[InputRequired(), Length(min=4, max=100)], render_kw={"placeholder": "email"})
    password = PasswordField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "password"})
    submit = SubmitField("Login")

class AddProductForm(FlaskForm):
    name = StringField('Название', validators=[InputRequired(), Length(max=100)])
    description = TextAreaField('Описание')
    photo = StringField('Фото', validators=[InputRequired()])
    category = SelectField('Категория', choices=[('Richard Mille', 'Richard Mille'), ('Rolex', 'Rolex'), ('Patek Philippe', 'Patek Philippe')], validators=[InputRequired()])
    price = DecimalField('Цена', validators=[InputRequired(), NumberRange(min=0)])
    submit = SubmitField('Добавить товар')

# decorators (routes)
@app.route('/')
def mainpage():
    products = Product.query.all()
    return render_template('mainpage.html', products=products, current_user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = loginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first() 
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('mainpage'))
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('mainpage'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = registerForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data)
        new_user = User(first_name=form.first_name.data, last_name=form.last_name.data, email=form.email.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/order')
@login_required
def order():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    products = {item.product_id: Product.query.get(item.product_id) for order in orders for item in order.order_items}
    
    for order in orders:
        order.total_cost = sum(item.quantity * item.price_at_order for item in order.order_items)
        
    return render_template('order.html', orders=orders, products=products)

@app.route('/create_order', methods=['POST'])
@login_required
def create_order():
    user_cart = current_user.cart
    if not user_cart:
        return redirect(url_for('cart'))

    cart_products = CartProduct.query.filter_by(entry_id=user_cart.id).all()
    if not cart_products:
        return redirect(url_for('cart'))

    delivery_address = request.form.get('delivery_address')

    new_order = Order(
        user_id=current_user.id,
        order_date=datetime.utcnow(),
        status="В обработке",
        delivery_address=delivery_address,
    )
    db.session.add(new_order)
    db.session.commit()

    total_cost = 0

    for cart_product in cart_products:
        product = Product.query.get(cart_product.product_id)
        
        order_item = OrderItem(
            order_id=new_order.id,
            product_id=cart_product.product_id,
            quantity=cart_product.quantity,
            price_at_order=product.price
        )
        db.session.add(order_item)
    
        db.session.delete(cart_product)

        total_cost += product.price * cart_product.quantity

    new_order.total_cost = total_cost

    db.session.commit()

    return redirect(url_for('order'))

@app.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('order_details.html', order=order)

@app.route('/cart')
@login_required
def cart():
    user_cart = current_user.cart
    if not user_cart:
        cart_items = []
    else:
        cart_products = CartProduct.query.filter_by(entry_id=user_cart.id).all()
        cart_items = []
        total_cost = 0
        for cart_product in cart_products:
            product = Product.query.get(cart_product.product_id)
            cart_items.append({
                'id': product.id,
                'name': product.name,
                'image': product.photo,
                'quantity': cart_product.quantity,
                'price': product.price
            })
            total_cost += product.price * cart_product.quantity

    return render_template('cart.html', cart_items=cart_items, total_cost=total_cost)

@app.route('/cart/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_cart(product_id):
    user_cart = current_user.cart
    if user_cart:
        cart_product = CartProduct.query.filter_by(entry_id=user_cart.id, product_id=product_id).first()
        if cart_product:
            db.session.delete(cart_product)
            db.session.commit()
    return redirect(url_for('cart'))

@app.route('/cart/increase/<int:product_id>', methods=['POST'])
@login_required
def increase_quantity(product_id):
    user_cart = current_user.cart
    if user_cart:
        cart_product = CartProduct.query.filter_by(entry_id=user_cart.id, product_id=product_id).first()
        if cart_product and cart_product.quantity < 100:
            cart_product.quantity += 1
            db.session.commit()
    return redirect(url_for('cart'))

@app.route('/cart/decrease/<int:product_id>', methods=['POST'])
@login_required
def decrease_quantity(product_id):
    user_cart = current_user.cart
    if user_cart:
        cart_product = CartProduct.query.filter_by(entry_id=user_cart.id, product_id=product_id).first()
        if cart_product and cart_product.quantity > 1:
            cart_product.quantity -= 1
            db.session.commit()
    return redirect(url_for('cart'))

@app.route('/category/<category_name>')
def category(category_name):
    products = Product.query.filter_by(category=category_name).all()
    return render_template('mainpage.html', products=products, current_category=category_name)

@app.route('/good/<int:product_id>', methods=['GET', 'POST'])
def good(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        if current_user.is_authenticated:
            quantity = int(request.form.get('quantity'))

            user_cart = current_user.cart
            if not user_cart:
                user_cart = Cart(user_id=current_user.id)
                db.session.add(user_cart)
                db.session.commit()

            cart_product = CartProduct.query.filter_by(entry_id=user_cart.id, product_id=product_id).first()

            if cart_product:
                cart_product.quantity += quantity
            else:
                cart_product = CartProduct(entry_id=user_cart.id, product_id=product_id, quantity=quantity)
                db.session.add(cart_product)

            db.session.commit()
            return redirect(url_for('cart'))
        else:
            return redirect(url_for('login'))

    return render_template('good.html', product=product)

@app.route('/export_cart')
@login_required
def export_cart():
    user_cart = current_user.cart
    if not user_cart:
        return redirect(url_for('cart'))

    cart_products = CartProduct.query.filter_by(entry_id=user_cart.id).all()

    csv_data = StringIO()
    csv_writer = csv.writer(csv_data)
    csv_writer.writerow(['Product Name', 'Quantity', 'Price'])

    for cart_product in cart_products:
        product = Product.query.get(cart_product.product_id)
        csv_writer.writerow([product.name, cart_product.quantity, product.price])

    headers = {
        "Content-Disposition": "attachment; filename=cart.csv",
        "Content-Type": "text/csv"
    }

    return Response(
        csv_data.getvalue(),
        headers=headers,
        mimetype="text/csv"
    )

@app.route('/admin_personal')
@login_required
def admin_personal():
    if not current_user.is_admin:
        return redirect(url_for('mainpage'))
    products = Product.query.all()
    return render_template('admin_personal.html', products=products)

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        return redirect(url_for('mainpage')) 
    
    form = AddProductForm()
    if form.validate_on_submit():
        new_product = Product(
            name=form.name.data,
            description=form.description.data,
            photo=form.photo.data,
            category=form.category.data,
            price=form.price.data
        )
        db.session.add(new_product)
        db.session.commit()
        return redirect(url_for('mainpage'))
    
    return render_template('add_product.html', form=form)

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        return redirect(url_for('mainpage'))
    
    product = Product.query.get_or_404(product_id)
    form = AddProductForm(obj=product)
    
    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.photo = form.photo.data
        product.category = form.category.data
        product.price = form.price.data
        db.session.commit()
        return redirect(url_for('mainpage'))
    
    return render_template('edit_product.html', form=form, product=product)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if not current_user.is_admin:
        return redirect(url_for('mainpage'))
    
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for('mainpage'))


# entry point
if __name__ == '__main__':
    app.run(debug=True)
