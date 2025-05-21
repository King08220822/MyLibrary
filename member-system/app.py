import pymongo
client=pymongo.MongoClient("mongodb+srv://king:king0822@cluster0.ajjhqnt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db=client.member_system
print("資料庫連線建立成功")
from flask import *
from bson import ObjectId#ObjectId是MongoDB的ID類型轉換工具
from datetime import datetime,timedelta##匯入時間處裡工具
import requests
from flask import jsonify
from collections import defaultdict
from flask import flash 
borrow_records=db["records"]

app=Flask(
    __name__,
)

app.secret_key = 'your-secret-key'
#處理路由
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/user-borrow-stats")
def user_borrow_stats():
    if "nickname" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    nickname = session["nickname"]
    records = db.records.find({"user": nickname})
    monthly_counts = defaultdict(int)

    for record in records:
        borrow_time = record.get("borrow_time")
        if borrow_time:
            month_key = borrow_time.strftime("%Y-%m")
            monthly_counts[month_key] += 1

    sorted_data = sorted(monthly_counts.items())
    return jsonify({
        "labels": [item[0] for item in sorted_data],
        "counts": [item[1] for item in sorted_data]
    })


#/error?msg=錯誤訊息
@app.route("/error")
def error():
    message=request.args.get("msg","發生錯誤請聯繫客服")
    return render_template("error.html",data=message)



@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        # 註冊處理邏輯
        nickname = request.form["nickname"]
        email = request.form["email"]
        password = request.form["password"]
        
        # 檢查 email 是否已註冊
        collection = db.users
        if collection.find_one({"email": email}):
            return redirect("/error?msg=信箱已被註冊")
        
        # 將用戶資料插入資料庫
        collection.insert_one({
            "nickname": nickname,
            "email": email,
            "password": password
        })
        
        return redirect("/signin")  # 註冊成功後跳轉到登入頁面
    return render_template("register.html")  # GET 請求時返回註冊頁面


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        # 處理用戶提交的登入表單
        email = request.form["email"]
        password = request.form["password"]
        
        collection = db.users
        result = collection.find_one({
            "$and": [
                {"email": email},
                {"password": password}
            ]
        })
        
        if result is None:
            return redirect("/error?msg=帳號或密碼輸入錯誤")
        
        session["nickname"] = result["nickname"]
        return redirect("/member")
    
    return render_template("index.html")

@app.route("/signout")
def signout():
    session.clear()
    return redirect("/")



@app.route("/add-book")
def add_book():
    if "nickname" not in session:
        return redirect("/")
    
    title = request.args.get("title")
    author = request.args.get("author")

    if not title or not author:
        return redirect("/error?msg=書籍資料不完整")

    db.books.insert_one({
        "title": title,
        "author": author,
        "status": "available",
        "added_by": session["nickname"] 
    })

    return redirect("/books")


@app.route("/books")
def books():
    if "nickname" not in session:
        return redirect("/")
    nickname=session["nickname"]
    book_list = list(db.books.find({"added_by":nickname}))#從mongodb中的books集合讀取所有書籍資料
    return render_template("books.html", books=book_list)


@app.route("/borrow/<book_id>")
def borrow(book_id):
    if "nickname" not in session:
        return redirect("/")
    book = db.books.find_one({"_id": ObjectId(book_id)})

    if not book:
        flash('⚠️ 書籍不存在。')
        return redirect(url_for('books'))

    if book['status'] == 'available':
        due_date = datetime.now() + timedelta(14)
        db.books.update_one(
            {'_id': ObjectId(book_id)},
            {'$set': {'status': 'borrowed', 'due_date': due_date}}
        )
        db.records.insert_one({
            "user": session["nickname"],
            "book_title": book["title"],
            "book_id": book["_id"],
            "borrow_time": datetime.now(),
            "due_date": due_date
        })
        flash(f'✅ Book borrowing successful! Please return it by {due_date.strftime("%Y-%m-%d")}.')
    else:
        flash('⚠️ 此書目前無法借閱，可能已被借出。')

    return redirect(url_for('books'))






@app.route("/delete-book/<book_id>")
def delete_book(book_id):
    if "nickname" not in session:
        return redirect("/")
    
    db.books.delete_one({"_id": ObjectId(book_id)})
    return redirect("/books")


@app.route("/records")
def records():
    if "nickname" not in session:
        return redirect("/")
    user_records = list(db.records.find({"user": session["nickname"]}))
    return render_template("records.html", records=user_records)

@app.route("/search-book", methods=["GET", "POST"])
def search_book():
    if "nickname" not in session:
        return redirect("/")
    
    
    books = []
    if request.method == "POST":
        query = request.form["query"]
        
        if query:
            # 使用 Open Library API 來搜尋書籍
            url = f"https://openlibrary.org/search.json?q={query}"
            response = requests.get(url)
            data = response.json()

            # 確保搜尋結果存在
            if 'docs' in data:
                books = data['docs']  # 取得書籍資料

    return render_template("search_book.html", books=books)
    
@app.route("/member")
def member():
    if 'nickname' not in session:
        return redirect("/")

    subject = "bestsellers"
    url = f"https://openlibrary.org/subjects/{subject}.json?limit=20"
    response = requests.get(url)
    books = []

    if response.ok:
        data = response.json()
        for work in data.get('works', []):
            title = work.get('title')
            cover_id = work.get('cover_id')
            key = work.get('key')
            authors = work.get('authors', [])
            rating = work.get('ratings_average')

            if not cover_id:
                continue  # 無封面跳過

            # 組作者字串
            author_names = ", ".join([author.get('name', 'Unknown') for author in authors])

            # 建立封面與連結
            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
            book_url = f"https://openlibrary.org{key}"

            books.append({
                'title': title,
                'author': author_names,
                'rating': rating,
                'cover': cover_url,
                'link': book_url
            })

    return render_template("member.html", nickname=session['nickname'], recommended_books=books)


@app.route('/borrowed_books')
def borrowed_books():
    username = session.get('nickname')
    if not username:
        return redirect(url_for('signin'))

    records = list(borrow_records.find({"user": username, "returned": {"$ne": True}}))

    borrowed_books = []
    now = datetime.utcnow()

    for record in records:
        due_date = record.get("due_date")
        if not due_date:
            continue

        days_left = (due_date - now).days

        borrowed_books.append({
            "book_id": str(record.get("book_id")),
            "book_title": record.get("book_title"),
            "due_date": due_date,
            "days_left": days_left,
            "returned": record.get("returned", False)
        })

    return render_template("borrowed_books.html", borrowed_books=borrowed_books)



@app.route('/return_book', methods=['POST'])
def return_book():
    username = session.get('nickname')  # 這邊要跟你 session 裡的 key 一致
    if not username:
        return redirect(url_for('signin'))

    book_id = request.form.get('book_id')
    if not book_id:
        return redirect(url_for('borrowed_books'))

    borrow_records.update_one(
        {"user": username, "book_id": ObjectId(book_id), "returned": {"$ne": True}},
        {"$set": {"returned": True, "return_time": datetime.utcnow()}}
    )
    flash('✅ Successfully returned the book!')
    return redirect(url_for('borrowed_books'))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

