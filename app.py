from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import pandas as pd
import joblib
import os
from datetime import datetime, timedelta
import json
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True, origins=['http://localhost:8080', 'http://localhost:3000'])

# MongoDB connection
MONGODB_PASSWORD = os.getenv('MONGODB_PASSWORD', 'GfyYjetkYLGEWR2u')
MONGODB_URI = f"mongodb+srv://kit27cse57_db_user:{MONGODB_PASSWORD}@nutridiet.rbvihzn.mongodb.net/?appName=NutriDiet"

try:
    client = MongoClient(MONGODB_URI)
    db = client['NutriDiet']
    collection = db['user_data']
    users_collection = db['users']
    client.admin.command('ping')
    print("[OK] Connected to MongoDB successfully!")
except Exception as e:
    print(f"[ERROR] MongoDB connection error: {e}")
    client = None
    db = None
    collection = None
    users_collection = None

# ✅ Define nutrient calculation here instead of importing
def calculate_nutrient_requirements(age, gender, height, weight, goal):
    """Calculate basic nutrient needs."""
    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if gender.lower() == "m" else -161)
    if goal.lower() == "weight_loss":
        calories = bmr - 300
    elif goal.lower() == "muscle_gain":
        calories = bmr + 300
    else:
        calories = bmr
    protein = (calories * 0.3) / 4
    fat = (calories * 0.25) / 9
    carbs = (calories * 0.45) / 4
    return calories, protein, fat, carbs


# MongoDB doesn't need schema migration, but we'll keep this function for compatibility
def migrate_database():
    """MongoDB doesn't require schema migration - it's schema-less."""
    pass


# ✅ Save user data in database (MongoDB) - optional, no authentication required
def save_user_data(name, gender, age, height, weight, goal, food_type, allergies,
                   calories, protein, fat, carbs, breakfast, lunch, dinner, user_id=None):
    if collection is None:
        print("[WARNING] MongoDB not available, using mock ID")
        return "mock_id_" + str(datetime.now().timestamp())
    
    try:
        user_document = {
            "name": name,
            "gender": gender,
            "age": age,
            "height": height,
            "weight": weight,
            "goal": goal,
            "food_type": food_type,
            "allergies": allergies,
            "calories": calories,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "breakfast": breakfast,
            "lunch": lunch,
            "dinner": dinner,
            "created_at": datetime.now()
        }
        
        # Add user_id only if provided (for authenticated users)
        if user_id:
            user_document["user_id"] = user_id
        
        result = collection.insert_one(user_document)
        return str(result.inserted_id)
    except Exception as e:
        print(f"[WARNING] Error saving to MongoDB: {e}")
        return "mock_id_" + str(datetime.now().timestamp())


# ✅ Get user data from database (MongoDB) - for specific user
def get_user_data(user_id=None, entry_id=None):
    if collection is None:
        return None
    
    if entry_id:
        try:
            user_doc = collection.find_one({"_id": ObjectId(entry_id)})
        except:
            return None
    elif user_id:
        # Get latest entry for this user
        user_doc = collection.find_one({"user_id": user_id}, sort=[("created_at", -1)])
    else:
        return None
    
    if not user_doc:
        return None
    
    user_doc["id"] = str(user_doc["_id"])
    del user_doc["_id"]
    return user_doc


# ✅ Get all user entries for dashboard (MongoDB) - for specific user only
def get_all_user_data(user_id):
    if collection is None:
        return []
    
    users = list(collection.find({"user_id": user_id}, sort=[("created_at", -1)]))
    
    for user in users:
        user["id"] = str(user["_id"])
        del user["_id"]
    
    return users


@app.route('/')
def home():
    return render_template('index.html')


# ✅ Authentication helper function
def get_current_user_id():
    """Get current logged-in user ID from session."""
    return session.get('user_id')


# ✅ Sign Up endpoint
@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        
        if not name or not email or not password:
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        if users_collection is None:
            return jsonify({'success': False, 'error': 'Database connection unavailable'}), 500
        
        # Check if user already exists
        existing_user = users_collection.find_one({"email": email})
        if existing_user:
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        
        # Create new user
        hashed_password = generate_password_hash(password)
        user_doc = {
            "name": name,
            "email": email,
            "password": hashed_password,
            "created_at": datetime.now()
        }
        
        result = users_collection.insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        # Set session
        session['user_id'] = user_id
        session['user_email'] = email
        session['user_name'] = name
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'name': name,
            'email': email
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ✅ Sign In endpoint
@app.route('/api/auth/signin', methods=['POST'])
def api_signin():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        if users_collection is None:
            return jsonify({'success': False, 'error': 'Database connection unavailable'}), 500
        
        # Find user
        user = users_collection.find_one({"email": email})
        if not user:
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Check password
        if not check_password_hash(user['password'], password):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Set session
        user_id = str(user['_id'])
        session['user_id'] = user_id
        session['user_email'] = email
        session['user_name'] = user.get('name', '')
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'name': user.get('name', ''),
            'email': email
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ✅ Sign Out endpoint
@app.route('/api/auth/signout', methods=['POST'])
def api_signout():
    session.clear()
    return jsonify({'success': True, 'message': 'Signed out successfully'})


# ✅ Check authentication status
@app.route('/api/auth/me', methods=['GET'])
def api_me():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'success': False, 'authenticated': False}), 401
    
    if users_collection is None:
        return jsonify({'success': False, 'authenticated': False}), 500
    
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            session.clear()
            return jsonify({'success': False, 'authenticated': False}), 401
        
        return jsonify({
            'success': True,
            'authenticated': True,
            'user_id': user_id,
            'name': user.get('name', ''),
            'email': user.get('email', '')
        })
    except:
        session.clear()
        return jsonify({'success': False, 'authenticated': False}), 401


# ✅ API endpoint for predictions (JSON) - no authentication required
@app.route('/api/predict', methods=['POST'])
def api_predict():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        # ✅ Get user input
        name = data.get('name', '')
        gender = data.get('gender', '').lower()
        age = int(data.get('age', 0))
        height = float(data.get('height', 0))
        weight = float(data.get('weight', 0))
        goal = data.get('healthGoal', '').lower().replace(' ', '_')
        food_type = data.get('foodPreferences', '')
        allergies = data.get('allergies', '')

        # ✅ Load dataset
        df = pd.read_csv("data/processed_diet.csv")

        # ✅ Load models
        breakfast_model = joblib.load("models/breakfast_model.pkl")
        lunch_model = joblib.load("models/lunch_model.pkl")
        dinner_model = joblib.load("models/dinner_model.pkl")

        # ✅ Filter allergies if any
        if allergies and allergies.lower() != "none" and allergies.strip():
            allergy_list = [a.strip() for a in allergies.split(",")]
            df = df[~df['food'].str.contains('|'.join(allergy_list), case=False, na=False)]

        # ✅ Calculate nutrient needs
        calories, protein, fat, carbs = calculate_nutrient_requirements(age, gender, height, weight, goal)

        # ✅ Features for model prediction
        features = [
            "Vitamin C (mg per 100g)",
            "Vitamin B11 (mg per 100g)",
            "Sodium (mg per 100g)",
            "Calcium (mg per 100g)",
            "Carbohydrates (g per 100g)",
            "Iron (mg per 100g)",
            "Calories (kcal per 100g)",
            "Sugars (g per 100g)",
            "Dietary Fiber (g per 100g)",
            "Fat (g per 100g)",
            "Protein (g per 100g)"
        ]

        # ✅ Predict clusters
        df['breakfast_cluster'] = breakfast_model.predict(df[features])
        df['lunch_cluster'] = lunch_model.predict(df[features])
        df['dinner_cluster'] = dinner_model.predict(df[features])

        # ✅ Select random recommendations
        breakfast_raw = df[df['breakfast_cluster'] == df['breakfast_cluster'].mode()[0]].sample(1).iloc[0]['food']
        lunch_raw = df[df['lunch_cluster'] == df['lunch_cluster'].mode()[0]].sample(1).iloc[0]['food']
        dinner_raw = df[df['dinner_cluster'] == df['dinner_cluster'].mode()[0]].sample(1).iloc[0]['food']
        
        # ✅ Format meal names: capitalize first letter of each word
        def format_meal_name(meal):
            return ' '.join(word.capitalize() for word in meal.split())
        
        breakfast = format_meal_name(breakfast_raw)
        lunch = format_meal_name(lunch_raw)
        dinner = format_meal_name(dinner_raw)

        # ✅ Calculate BMI and BMR
        height_in_meters = height / 100
        bmi = weight / (height_in_meters * height_in_meters)
        bmr = 10 * weight + 6.25 * height - 5 * age + (5 if gender == "m" or gender == "male" else -161)

        # ✅ Save user data (optional - no authentication required)
        # Recommendations are based solely on CSV data and ML models
        entry_id = save_user_data(name, gender, age, height, weight, goal, food_type, allergies,
                                 calories, protein, fat, carbs, breakfast, lunch, dinner)

        # ✅ Return JSON response
        return jsonify({
            'success': True,
            'entry_id': entry_id,
            'bmi': round(bmi, 1),
            'bmr': round(bmr),
            'calories': round(calories),
            'protein': round(protein),
            'fat': round(fat),
            'carbs': round(carbs),
            'meals': [breakfast, lunch, dinner],
            'breakfast': breakfast,
            'lunch': lunch,
            'dinner': dinner
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ✅ API endpoint for dashboard data
@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    try:
        user_id = request.args.get('user_id', type=str)
        user_data = get_user_data(user_id) if user_id else get_user_data()
        
        if not user_data:
            return jsonify({
                'success': False,
                'message': 'No user data found'
            }), 404

        # Calculate BMI
        height_in_meters = user_data['height'] / 100
        bmi = user_data['weight'] / (height_in_meters * height_in_meters)
        
        # Get BMI category
        if bmi < 18.5:
            bmi_category = "Underweight"
        elif bmi < 25:
            bmi_category = "Normal weight"
        elif bmi < 30:
            bmi_category = "Overweight"
        else:
            bmi_category = "Obese"

        # Generate historical data (simulated based on goal)
        weight_data = []
        bmi_data = []
        calorie_data = []
        goal_data = []
        
        # Get all entries for this user or latest user
        all_data = get_all_user_data()
        current_user_entries = [d for d in all_data if d.get('name') == user_data.get('name')]
        
        if len(current_user_entries) > 1:
            # Use actual historical data
            for i, entry in enumerate(current_user_entries[-8:]):  # Last 8 entries
                date = datetime.now() - timedelta(weeks=len(current_user_entries) - i - 1)
                entry_bmi = entry['weight'] / ((entry['height'] / 100) ** 2)
                weight_data.append({
                    'date': date.strftime('%b %d'),
                    'weight': entry['weight'],
                    'goal': user_data['weight'] - 5 if user_data['goal'] == 'weight_loss' else user_data['weight']
                })
                bmi_data.append({
                    'date': date.strftime('%b %d'),
                    'bmi': round(entry_bmi, 1),
                    'category': bmi_category
                })
        else:
            # Generate simulated data
            goal_weight = user_data['weight'] - 5 if 'weight_loss' in user_data['goal'].lower() else user_data['weight']
            for i in range(8):
                date = datetime.now() - timedelta(weeks=7-i)
                simulated_weight = user_data['weight'] - (i * 0.5)
                simulated_bmi = simulated_weight / (height_in_meters ** 2)
                weight_data.append({
                    'date': date.strftime('%b %d'),
                    'weight': round(simulated_weight, 1),
                    'goal': goal_weight
                })
                bmi_data.append({
                    'date': date.strftime('%b %d'),
                    'bmi': round(simulated_bmi, 1),
                    'category': bmi_category
                })

        # Generate weekly calorie data
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for day in days:
            calorie_data.append({
                'date': day,
                'consumed': round(user_data['calories'] * (0.9 + (hash(day) % 20) / 100), 0),
                'burned': round(user_data['calories'] * 1.1 + (hash(day) % 200), 0),
                'target': round(user_data['calories'], 0)
            })

        # Goal achievements
        goal_data = [
            {'goal': 'Daily Steps', 'achieved': 85, 'target': 100},
            {'goal': 'Water Intake', 'achieved': 92, 'target': 100},
            {'goal': 'Meal Planning', 'achieved': 78, 'target': 100},
            {'goal': 'Sleep Hours', 'achieved': 70, 'target': 100},
            {'goal': 'Exercise', 'achieved': 88, 'target': 100}
        ]

        current_weight = weight_data[-1]['weight'] if weight_data else user_data['weight']
        start_weight = weight_data[0]['weight'] if weight_data else user_data['weight']
        weight_change = start_weight - current_weight
        goal_weight = weight_data[0]['goal'] if weight_data else (user_data['weight'] - 5 if 'weight_loss' in user_data['goal'].lower() else user_data['weight'])
        goal_progress = ((start_weight - current_weight) / (start_weight - goal_weight) * 100) if (start_weight - goal_weight) > 0 else 0

        return jsonify({
            'success': True,
            'user': {
                'name': user_data['name'],
                'weight': user_data['weight'],
                'height': user_data['height'],
                'age': user_data['age'],
                'gender': user_data['gender'],
                'goal': user_data['goal']
            },
            'stats': {
                'current_weight': current_weight,
                'start_weight': start_weight,
                'weight_change': round(weight_change, 1),
                'current_bmi': round(bmi, 1),
                'bmi_category': bmi_category,
                'goal_progress': round(max(0, min(100, goal_progress)), 0),
                'tracking_days': len(weight_data) * 7
            },
            'charts': {
                'weight_data': weight_data,
                'bmi_data': bmi_data,
                'calorie_data': calorie_data,
                'goal_data': goal_data
            },
            'nutrients': {
                'calories': round(user_data['calories'], 0),
                'protein': round(user_data['protein'], 0),
                'fat': round(user_data['fat'], 0),
                'carbs': round(user_data['carbs'], 0)
            },
            'meals': {
                'breakfast': user_data['breakfast'],
                'lunch': user_data['lunch'],
                'dinner': user_data['dinner']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ✅ API endpoint to get meal details
@app.route('/api/meal-details', methods=['GET'])
def api_meal_details():
    try:
        meal_name = request.args.get('meal', '').strip()
        if not meal_name:
            return jsonify({'success': False, 'error': 'Meal name is required'}), 400
        
        # Load dataset
        df = pd.read_csv("data/processed_diet.csv")
        
        # Format meal name for search (lowercase, remove extra spaces)
        # Handle both formatted (e.g., "Margarine With Yoghurt") and unformatted names
        meal_name_lower = ' '.join(meal_name.lower().split())
        
        # Try to find exact match first (case-insensitive)
        meal_row = df[df['food'].str.lower().str.strip() == meal_name_lower]
        
        # If no exact match, try case-insensitive partial match
        if meal_row.empty:
            meal_row = df[df['food'].str.lower().str.contains(meal_name_lower, case=False, na=False)]
        
        if meal_row.empty:
            return jsonify({'success': False, 'error': f'Meal "{meal_name}" not found in database'}), 404
        
        # Get first match
        meal_data = meal_row.iloc[0]
        
        # Format meal name for display
        def format_meal_name(meal):
            return ' '.join(word.capitalize() for word in meal.split())
        
        meal_name_formatted = format_meal_name(meal_data['food'])
        
        return jsonify({
            'success': True,
            'meal': {
                'name': meal_name_formatted,
                'calories': round(float(meal_data['Calories (kcal per 100g)']), 1),
                'protein': round(float(meal_data['Protein (g per 100g)']), 1),
                'fat': round(float(meal_data['Fat (g per 100g)']), 1),
                'carbohydrates': round(float(meal_data['Carbohydrates (g per 100g)']), 1),
                'dietaryFiber': round(float(meal_data['Dietary Fiber (g per 100g)']), 1),
                'sugars': round(float(meal_data['Sugars (g per 100g)']), 1),
                'vitaminC': round(float(meal_data['Vitamin C (mg per 100g)']), 2),
                'vitaminB11': round(float(meal_data['Vitamin B11 (mg per 100g)']), 2),
                'sodium': round(float(meal_data['Sodium (mg per 100g)']), 2),
                'calcium': round(float(meal_data['Calcium (mg per 100g)']), 1),
                'iron': round(float(meal_data['Iron (mg per 100g)']), 2)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ✅ API endpoint to get latest user
@app.route('/api/user/latest', methods=['GET'])
def api_user_latest():
    try:
        user_data = get_user_data()
        if not user_data:
            return jsonify({'success': False, 'message': 'No user data found'}), 404
        
        return jsonify({'success': True, 'user': user_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ✅ Legacy route for form submission (kept for backward compatibility)
@app.route('/predict', methods=['POST'])
def predict():
    # ✅ Get user input
    name = request.form['name']
    gender = request.form['gender']
    age = int(request.form['age'])
    height = float(request.form['height'])
    weight = float(request.form['weight'])
    goal = request.form['goal']
    food_type = request.form['food_type']
    allergies = request.form.get('allergies', '')

    # ✅ Load dataset
    df = pd.read_csv("data/processed_diet.csv")

    # ✅ Load models
    breakfast_model = joblib.load("models/breakfast_model.pkl")
    lunch_model = joblib.load("models/lunch_model.pkl")
    dinner_model = joblib.load("models/dinner_model.pkl")

    # ✅ Filter allergies if any
    if allergies and allergies.lower() != "none":
        allergy_list = [a.strip() for a in allergies.split(",")]
        df = df[~df['food'].str.contains('|'.join(allergy_list), case=False, na=False)]

    # ✅ Calculate nutrient needs
    calories, protein, fat, carbs = calculate_nutrient_requirements(age, gender, height, weight, goal)

    # ✅ Features for model prediction
    features = [
        "Vitamin C (mg per 100g)",
        "Vitamin B11 (mg per 100g)",
        "Sodium (mg per 100g)",
        "Calcium (mg per 100g)",
        "Carbohydrates (g per 100g)",
        "Iron (mg per 100g)",
        "Calories (kcal per 100g)",
        "Sugars (g per 100g)",
        "Dietary Fiber (g per 100g)",
        "Fat (g per 100g)",
        "Protein (g per 100g)"
    ]

    # ✅ Predict clusters (not used, but shows model usage)
    df['breakfast_cluster'] = breakfast_model.predict(df[features])
    df['lunch_cluster'] = lunch_model.predict(df[features])
    df['dinner_cluster'] = dinner_model.predict(df[features])

    # ✅ Select random recommendations
    breakfast = df[df['breakfast_cluster'] == df['breakfast_cluster'].mode()[0]].sample(1).iloc[0]['food']
    lunch = df[df['lunch_cluster'] == df['lunch_cluster'].mode()[0]].sample(1).iloc[0]['food']
    dinner = df[df['dinner_cluster'] == df['dinner_cluster'].mode()[0]].sample(1).iloc[0]['food']

    # ✅ Save user data
    save_user_data(name, gender, age, height, weight, goal, food_type, allergies,
                   calories, protein, fat, carbs, breakfast, lunch, dinner)

    # ✅ Show output to user
    return render_template('index.html',
                           name=name,
                           calories=round(calories),
                           protein=round(protein),
                           fat=round(fat),
                           carbs=round(carbs),
                           breakfast=breakfast,
                           lunch=lunch,
                           dinner=dinner)


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
