from fastapi import FastAPI, HTTPException, status, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import sqlite3
from typing import List, Optional
from datetime import datetime, timedelta

# FastAPI instance
app = FastAPI()

# OAuth2 password bearer for token authentication
oauth_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Database setup
DATABASE = 'users.db'

# Helper function to get database connection
def get_db():
    db_connection = sqlite3.connect(DATABASE, check_same_thread=False)
    db_connection.row_factory = sqlite3.Row  # Enable access by column name
    return db_connection

# Dish model
class Dish(BaseModel):
    id: int
    name: str
    category_id: int
    availability: bool
    stock: Optional[int] = None  # Add stock attribute

# ========================
# Dish Management Routes
# ========================

@app.get("/dishes", response_model=List[Dish], tags=["Dish Management"])
async def get_dishes(
    category_id: int = Query(None, description="Filter by category ID"),
    availability: bool = Query(None, description="Filter by availability (true/false)")
):
    db = get_db()
    cursor = db.cursor()

    query = "SELECT * FROM dishes WHERE 1=1"
    params = []

    if category_id is not None:
        query += " AND category_id = ?"
        params.append(category_id)

    if availability is not None:
        query += " AND availability = ?"
        params.append(availability)

    cursor.execute(query, tuple(params))
    dishes = cursor.fetchall()
    db.close()

    return [dict(dish) for dish in dishes]


@app.post("/dishes", response_model=Dish, tags=["Dish Management"])
async def add_dish(dish: Dish, token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM dishes WHERE name = ? AND category_id = ?', (dish.name, dish.category_id))
    if cursor.fetchone():
        db.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dish with this name already exists in the category")

    cursor.execute(
        'INSERT INTO dishes (name, category_id, availability, stock) VALUES (?, ?, ?, ?)',
        (dish.name, dish.category_id, dish.availability, dish.stock)
    )
    db.commit()
    dish_id = cursor.lastrowid
    db.close()

    return JSONResponse(
        content={"message": "Dish added successfully", "dish": {"id": dish_id, **dish.dict()}},
        status_code=status.HTTP_201_CREATED
    )


@app.put("/dishes/{dish_id}", response_model=Dish, tags=["Dish Management"])
async def update_dish(dish_id: int, updated_dish: Dish, token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        '''
        UPDATE dishes
        SET name = ?, category_id = ?, availability = ?, stock = ?
        WHERE id = ?
        ''',
        (updated_dish.name, updated_dish.category_id, updated_dish.availability, updated_dish.stock, dish_id)
    )
    db.commit()

    if cursor.rowcount == 0:
        db.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dish not found")

    db.close()
    return JSONResponse(
        content={"message": "Dish updated successfully", "dish": updated_dish.dict()},
        status_code=status.HTTP_200_OK
    )


@app.delete("/dishes/{dish_id}", tags=["Dish Management"])
async def delete_dish(dish_id: int, token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    cursor.execute('DELETE FROM dishes WHERE id = ?', (dish_id,))
    db.commit()

    if cursor.rowcount == 0:
        db.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dish not found")

    db.close()
    return JSONResponse(content={"message": "Dish deleted successfully"}, status_code=status.HTTP_200_OK)
    
    
@app.get("/dishes/{dish_id}", response_model=Dish, tags=["Dish Management"])
async def get_dish_by_id(dish_id: int):
    """
    Fetch a single dish by its ID.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM dishes WHERE id = ?', (dish_id,))
    dish = cursor.fetchone()
    db.close()

    if not dish:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Dish with ID {dish_id} not found"
        )

    return dict(dish)


# ========================
# Dish Inventory Management APIs
# ========================

@app.patch("/menu/dishes/{dish_id}/out-of-stock", tags=["Dish Inventory Management"])
async def mark_dish_out_of_stock(dish_id: int):
    """
    Mark a dish as out of stock.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('UPDATE dishes SET availability = 0 WHERE id = ?', (dish_id,))
    db.commit()

    if cursor.rowcount == 0:
        db.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dish not found")

    db.close()
    return JSONResponse(content={"message": f"Dish with ID {dish_id} marked as out of stock"}, status_code=status.HTTP_200_OK)


@app.patch("/menu/dishes/{dish_id}/stock", tags=["Dish Inventory Management"])
async def update_dish_stock(dish_id: int, stock: int):
    """
    Update the stock quantity of a dish.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('UPDATE dishes SET stock = ? WHERE id = ?', (stock, dish_id))
    db.commit()

    if cursor.rowcount == 0:
        db.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dish not found")

    db.close()
    return JSONResponse(content={"message": f"Stock for dish with ID {dish_id} updated to {stock}"}, status_code=status.HTTP_200_OK)


@app.get("/admin/dishes/out-of-stock", tags=["Dish Inventory Management"])
async def get_out_of_stock_dishes(token: str = Depends(oauth_scheme)):
    """
    Retrieve a list of out-of-stock dishes.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM dishes WHERE availability = 0')
    dishes = cursor.fetchall()
    db.close()

    if not dishes:
        return JSONResponse(content={"message": "No out-of-stock dishes found"}, status_code=status.HTTP_200_OK)

    return [dict(dish) for dish in dishes]


# ========================
# Analytics & Reports APIs (Admin)
# ========================


@app.get("/admin/reports/inventory", tags=["Reports"])
async def get_inventory_report(token: str = Depends(oauth_scheme)):  # Adding token dependency here
    """
    Get the inventory report showing in-stock and out-of-stock dishes.
    """
    db = get_db()
    cursor = db.cursor()

    # Query for inventory summary
    cursor.execute('''
        SELECT
            (SELECT COUNT(*) FROM dishes WHERE availability = 1) AS in_stock,
            (SELECT COUNT(*) FROM dishes WHERE availability = 0) AS out_of_stock
    ''')

    inventory_data = cursor.fetchone()
    db.close()

    if not inventory_data:
        return JSONResponse(content={"message": "No inventory data found"}, status_code=status.HTTP_200_OK)

    return {
        "in_stock": inventory_data["in_stock"],
        "out_of_stock": inventory_data["out_of_stock"]
    }


# ========================
# Authentication & Authorization
# ========================

@app.post("/token")
async def token_generate(form_data: OAuth2PasswordRequestForm = Depends()):
    # Example: We return the username as the access token (in a real-world scenario, JWT tokens are recommended)
    return {"access_token": form_data.username, "token_type": "bearer"}


# ========================
# Lifecycle Events
# ========================

@app.on_event("startup")
async def startup():
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS dishes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        category_id INTEGER NOT NULL,
        availability BOOLEAN NOT NULL,
        stock INTEGER DEFAULT 0,
        FOREIGN KEY (category_id) REFERENCES categories (id)
    );''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS sales (
        sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        dish_id INTEGER,
        quantity INTEGER,
        price_per_item REAL,
        sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (order_id) REFERENCES orders (order_id),
        FOREIGN KEY (dish_id) REFERENCES dishes (id)
    );''')

    categories = {
        1: 'Appetizer', 2: 'Veg Curries', 3: 'Pickles', 4: 'Veg Fry', 5: 'Dal',
        6: 'Non Veg Curries', 7: 'Veg Rice', 8: 'Non-Veg Rice', 9: 'Veg Pulusu', 10: 'Breads', 11: 'Desserts',
    }

    dishes = [
        {"id": 1, "name": "Onion Pakoda", "category_id": 1, "availability": True, "stock": 10},
        {"id": 2, "name": "Mixed Veg Pakoda", "category_id": 1, "availability": True, "stock": 15},
    ]

    for id, name in categories.items():
        cursor.execute('INSERT OR IGNORE INTO categories (id, name) VALUES (?, ?)', (id, name))

    for dish in dishes:
        cursor.execute('''INSERT OR IGNORE INTO dishes (id, name, category_id, availability, stock)
            VALUES (?, ?, ?, ?, ?)''', (dish["id"], dish["name"], dish["category_id"], dish["availability"], dish["stock"]))

    db.commit()
    db.close()
    print("Database initialized with predefined categories and dishes")

@app.on_event("shutdown")
async def shutdown():
    db = get_db()
    db.close()
