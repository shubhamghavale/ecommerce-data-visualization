from flask import Flask, jsonify, request
from pymongo import MongoClient
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

# Connect to MongoDB
client = MongoClient("mongodb+srv://db_user_read:zHLuO45zk1upaRmp@cluster0.aaflc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client['RQ_Analytics']
customers_collection = db['shopifyCustomers']
orders_collection = db['shopifyOrders']

# Helper Functions
def format_date(date_str, interval):
    """Format date based on the given interval."""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None

    if interval == "daily":
        return date.strftime("%Y-%m-%d")
    elif interval == "monthly":
        return date.strftime("%Y-%m")
    elif interval == "quarterly":
        return f"Q{(date.month-1)//3 + 1}-{date.year}"
    elif interval == "yearly":
        return date.strftime("%Y")
    else:
        return date.strftime("%Y-%m-%d")

def format_interval(interval):
    """Return MongoDB date format string based on interval."""
    if interval == "daily":
        return "%Y-%m-%d"
    elif interval == "monthly":
        return "%Y-%m"
    elif interval == "quarterly":
        return "%Y-Q%q"
    elif interval == "yearly":
        return "%Y"
    else:
        return "%Y-%m-%d"

def calculate_growth_rate(data):
    """Calculate growth rate as percentage change between periods."""
    growth_rate = {}
    sorted_data = sorted(data.items())

    for i in range(1, len(sorted_data)):
        current_period = sorted_data[i][0]
        previous_period = sorted_data[i - 1][0]
        current_value = sorted_data[i][1]
        previous_value = sorted_data[i - 1][1]

        if previous_value > 0:
            rate = ((current_value - previous_value) / previous_value) * 100
        else:
            rate = 0

        growth_rate[current_period] = rate

    return growth_rate

# API Endpoints
@app.route('/api/total-sales', methods=['GET'])
def total_sales():
    """Total Sales Over Time grouped by a given interval."""
    try:
        interval = request.args.get('interval', 'daily')
        pipeline = [
            {
                '$addFields': {
                    'created_at_date': {
                        '$dateFromString': {
                            'dateString': '$created_at',
                            'format': '%Y-%m-%dT%H:%M:%S%z'
                        }
                    }
                }
            },
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': format_interval(interval),
                            'date': '$created_at_date'
                        }
                    },
                    'totalSales': {'$sum': {'$toDouble': '$total_price_set.shop_money.amount'}}
                }
            },
            {'$sort': {'_id': 1}}
        ]
        sales_data = list(orders_collection.aggregate(pipeline))
        return jsonify(sales_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sales-growth-rate', methods=['GET'])
def sales_growth_rate():
    """Sales Growth Rate Over Time."""
    try:
        interval = request.args.get('interval', 'daily')
        orders = list(orders_collection.find({}, {'total_price_set.shop_money.amount': 1, 'created_at': 1}))

        # Format sales data
        sales_data = {}
        for order in orders:
            date_key = format_date(order['created_at'], interval)
            if date_key:
                amount = float(order['total_price_set']['shop_money']['amount'])
                sales_data[date_key] = sales_data.get(date_key, 0) + amount

        # Calculate growth rate
        growth_rate_data = calculate_growth_rate(sales_data)

        return jsonify(growth_rate_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/new-customers', methods=['GET'])
def new_customers():
    """New Customers Added Over Time based on created_at field."""
    try:
        interval = request.args.get('interval', 'daily')
        customers = list(customers_collection.find({}, {'created_at': 1}))

        new_customers_data = {}
        for customer in customers:
            date_key = format_date(customer['created_at'], interval)
            if date_key:
                new_customers_data[date_key] = new_customers_data.get(date_key, 0) + 1

        return jsonify(sorted(new_customers_data.items()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/repeat-customers', methods=['GET'])
def repeat_customers():
    """Number of Repeat Customers over different time frames."""
    try:
        interval = request.args.get('interval', 'daily')
        orders = list(orders_collection.find({}, {'customer.id': 1, 'created_at': 1}))

        customer_order_count = {}
        repeat_customers_data = {}

        # Count orders for each customer
        for order in orders:
            customer_id = order['customer']['id']
            date_key = format_date(order['created_at'], interval)
            if date_key:
                if customer_id not in customer_order_count:
                    customer_order_count[customer_id] = {"count": 0, "first_order": date_key}
                
                customer_order_count[customer_id]["count"] += 1

        # Collect repeat customers by interval
        for customer_id, data in customer_order_count.items():
            if data["count"] > 1:
                date_key = data["first_order"]
                repeat_customers_data[date_key] = repeat_customers_data.get(date_key, 0) + 1

        return jsonify(sorted(repeat_customers_data.items()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/geographical-distribution', methods=['GET'])
def geographical_distribution():
    """Geographical Distribution of Customers."""
    try:
        customers = list(customers_collection.find({}, {'default_address.city': 1}))
        city_distribution = {}
        
        for customer in customers:
            city = customer['default_address'].get('city', 'Unknown')
            city_distribution[city] = city_distribution.get(city, 0) + 1

        return jsonify(city_distribution)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/customer-lifetime-value', methods=['GET'])
def customer_lifetime_value():
    """Customer Lifetime Value by Cohorts."""
    try:
        interval = request.args.get('interval', 'monthly')
        orders = list(orders_collection.find({}, {'customer.id': 1, 'total_price_set.shop_money.amount': 1, 'created_at': 1}))

        # Calculate total spent by each customer
        customer_lifetime_value_data = {}
        for order in orders:
            customer_id = order['customer']['id']
            date_key = format_date(order['created_at'], interval)
            amount = float(order['total_price_set']['shop_money']['amount'])
            
            if customer_id not in customer_lifetime_value_data:
                customer_lifetime_value_data[customer_id] = {"first_purchase": date_key, "total_spent": 0}
            
            customer_lifetime_value_data[customer_id]["total_spent"] += amount

        # Group customers by cohorts based on their first purchase
        cohorts = {}
        for customer_id, data in customer_lifetime_value_data.items():
            cohort = data["first_purchase"]
            total_spent = data["total_spent"]
            if cohort not in cohorts:
                cohorts[cohort] = 0
            cohorts[cohort] += total_spent

        return jsonify(cohorts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
