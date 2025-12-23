import os
from flask import Flask, render_template, request, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import csv
from io import StringIO

app = Flask(__name__)
app.secret_key = 'supersecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///azar.db'
db = SQLAlchemy(app)

# ===== Models =====
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))
    role = db.Column(db.String(20))

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    amount = db.Column(db.Float)
    interest = db.Column(db.Float)
    fees = db.Column(db.Float)
    total = db.Column(db.Float)
    status = db.Column(db.String(20))
    assigned_collector = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===== Initialize DB and default users =====
db.create_all()
if not User.query.filter_by(username='admin').first():
    admin = User(username='admin', password='1234', role='admin')
    collector1 = User(username='alice', password='alice123', role='collector')
    collector2 = User(username='bob', password='bob123', role='collector')
    db.session.add_all([admin, collector1, collector2])
    db.session.commit()

# ===== Routes =====
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['username'] = user.username
            session['role'] = user.role
            if user.role == 'admin':
                return redirect(url_for('admin'))
            elif user.role == 'collector':
                return redirect(url_for('collector'))
        return "Invalid credentials"
    return render_template('index.html')

@app.route('/apply', methods=['POST'])
def apply():
    name = request.form['name']
    phone = request.form['phone']
    amount = float(request.form['amount'])
    
    # Loan calculations
    interest = round(amount * 0.028)  # 2.8%
    total_repayment = 60000  # Hardcoded example, can calculate dynamically
    fees = round(total_repayment - amount - interest)
    total = amount + interest + fees
    
    loan = Loan(name=name, phone=phone, amount=amount, interest=interest, fees=fees, total=total, status='pending')
    db.session.add(loan)
    db.session.commit()
    
    due_date = loan.created_at + timedelta(days=7)
    
    return f"""
    Loan applied.<br>
    Total repay (7 days): UGX {total}<br>
    Due date: {due_date.strftime('%Y-%m-%d %H:%M')}<br>
    <a href='tel:*165*1*{amount}#'>DISBURSE</a> | 
    <a href='tel:*165*3*1*256761263253*{total}#'>REPAY</a>
    """

@app.route('/admin')
def admin():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    loans = Loan.query.all()
    total_profit = sum(l.interest + l.fees for l in loans)
    return render_template('admin.html', loans=loans, profit=total_profit)

@app.route('/assign/<int:loan_id>/<collector>')
def assign(loan_id, collector):
    loan = Loan.query.get(loan_id)
    loan.assigned_collector = collector
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/collector')
def collector():
    if 'role' not in session or session['role'] != 'collector':
        return redirect(url_for('login'))
    loans = Loan.query.filter_by(assigned_collector=session['username']).all()
    return render_template('collector.html', loans=loans)

@app.route('/paid/<int:loan_id>')
def mark_paid(loan_id):
    loan = Loan.query.get(loan_id)
    due_date = loan.created_at + timedelta(days=7)
    late_fee = 0
    if datetime.utcnow() > due_date:
        late_days = (datetime.utcnow() - due_date).days
        late_fee = late_days * 2500
    loan.total += late_fee
    loan.status = 'paid'
    db.session.commit()
    return redirect(request.referrer)

@app.route('/download_financials')
def download_financials():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    loans = Loan.query.all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Loan ID','Name','Phone','Principal','Interest','Fees','Late Fees','Total','Tax','Net Profit','Status','Collector'])
    
    for l in loans:
        due_date = l.created_at + timedelta(days=7)
        late_fee = 0
        if datetime.utcnow() > due_date and l.status != 'paid':
            late_days = (datetime.utcnow() - due_date).days
            late_fee = late_days * 2500
        tax = round(0.18 * (l.interest + l.fees + late_fee))
        net_profit = l.interest + l.fees + late_fee - tax
        writer.writerow([l.id, l.name, l.phone, l.amount, l.interest, l.fees, late_fee, l.total, tax, net_profit, l.status, l.assigned_collector or ""])
    
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=financial_statements.csv"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
