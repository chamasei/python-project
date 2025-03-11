from flask import Flask, request, session,render_template, redirect, url_for, flash,jsonify
from markupsafe import Markup
import subprocess
import logging
import sys
import re
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
import os
from functools import wraps  
from sqlalchemy import func
from sqlalchemy.engine.row import Row
import markdown
import psycopg2
import traceback
from flask_migrate import Migrate
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool  
from models import Question, Category, DifficultyLevel 



# ログ設定
logging.basicConfig(
    filename="execution.log",         # ログファイル名
    level=logging.DEBUG,               # ログレベル
    format="%(asctime)s - %(levelname)s - %(message)s"  # フォーマット
)

db = SQLAlchemy()

# ✅ 環境変数の読み込み
env_path = os.path.abspath(".env")
load_dotenv(".env")

# `.env` を強制的にロード
if not load_dotenv(env_path):
    print("🚨 `.env` の読み込みに失敗しました！")


def create_app():
    app = Flask(__name__)  # ✅ `Flask` インスタンスを関数内で作成



    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    
    if FLASK_ENV == "production":
        DATABASE_URL = os.getenv("DATABASE_URL")  # 本番環境のDB

        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        if "sslmode" not in DATABASE_URL:
            DATABASE_URL += "?sslmode=require"      
    else:
        DATABASE_URL= os.getenv("DATABASE_URL") # ローカルのDB
        
    
    # ✅ PostgreSQL の場合、接続URLの修正

    # ✅ Flask の設定
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": NullPool  # ✅ 使い終わった接続をすぐに閉じる！
    }

    # ✅ `SQLAlchemy` と `Flask` の関連付け
    db.init_app(app)
    migrate = Migrate(app, db)



    # ✅ `app.app_context()` の中で `models.py` を読み込む
    with app.app_context():
        from models import Question, Category, DifficultyLevel  
        db.create_all()  # ✅ テーブルを作成！

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()  # ✅ すべてのリクエストが終わったら、確実にセッションを閉じる！

    return app

app = create_app()  # ✅ `create_app()` を使って Flask アプリを作成

from sqlalchemy import text
@app.route("/debug-db4")
def debug_db4():
    try:
        question = db.session.execute(text("SELECT description FROM public.questions WHERE id=1")).fetchone()
        if question:
            processed_description = detect_code_blocks(question[0])  # ✅ コードブロック変換
            print("🚀 Jinja に渡す直前:", repr(processed_description))  # ✅ Jinja に渡すデータを表示
            
            return render_template("test.html", description=processed_description)
        else:
            return "❌ データが見つかりません"
    except Exception as e:
        return f"🚨 エラー発生: {str(e)}"





#dbのセッション管理
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()  # ✅ すべてのリクエストが終わったらセッションを解放！



#管理者用
# ✅ 環境変数から secret_key を取得（設定がなければ "your_secret_key_here" を使う）
app.secret_key = os.getenv("FLASK_SECRET_KEY") 
ADMIN_PASSWORD = os.getenv("PYTHON_ADMIN_PASSWORD")

def get_db_connection():
    DATABASE_URL = os.getenv("DATABASE_URL")  # 環境変数から取得

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in environment variables")

    conn = psycopg2.connect(DATABASE_URL)  # PostgreSQL に接続
    return conn


#それぞれのページで管理者ログインを要求する
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash("⚠️ 管理者ログインが必要です。", "error")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

#/admin以下は管理者ログインを求める
@app.before_request
def restrict_admin_routes():
    if request.path.startswith("/admin/") and not session.get('admin_logged_in'):
        # ✅ `/admin/login` と `/admin/logout` は除外
        if request.path not in [url_for('admin_login'), url_for('admin_logout')]:
            flash("⚠️ 管理者ログインが必要です。", "error")
            return redirect(url_for('admin_login'))


#管理者ログインのルート
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':
        password = request.form.get('password')

        stored_password = os.getenv("PYTHON_ADMIN_PASSWORD")

        
        if stored_password is None:
            flash("⚠️ サーバーの設定エラー: 環境変数が読み込めていません！", "error")
            return redirect(url_for('admin_login'))

        if password == stored_password:
            session['admin_logged_in'] = True
            session.permanent = False
            return redirect(url_for('manage_questions'))
        else:
            flash("⚠️ パスワードが違います。", "error")
        

    return render_template('admin_login.html')


@admin_required
def manage_questions():
    conn = get_db_connection()  # PostgreSQL に接続
    cur = conn.cursor()

    cur.execute('''
        SELECT questions.id, questions.question, categories.name AS category_name, difficulty_levels.name AS difficulty_name
        FROM questions
        LEFT JOIN categories ON questions.category_id = categories.id
        LEFT JOIN difficulty_levels ON questions.difficulty_id = difficulty_levels.id
    ''')
    questions = cur.fetchall()  # 変更: fetchall() をカーソルで取得
    cur.close()
    conn.close()

    return render_template('manage_questions.html', questions=questions)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("✅ ログアウトしました。", "success")
    return redirect(url_for('admin_login'))


def detect_code_blocks(description):
    formatted_parts = []
    in_code_block = False
    lines = description.split("\n")
    
        # ✅ コードブロック内の処理
    for line in lines:
        
        stripped_line = line.strip()
        if re.match(r"^\s*```", line):  # ✅ コードブロックの開始・終了を優先！
            if in_code_block:
                formatted_parts.append("</code></pre>")  # ✅ コードブロックを閉じる
                
            else:
                formatted_parts.append("<pre><code>")  # ✅ コードブロックを開始
            in_code_block = not in_code_block  # ✅ フラグを反転
            continue  # ✅ 他の処理をスキップして次の行へ！

        if in_code_block:  # ✅ コードブロック内ならそのまま追加
            formatted_parts.append(line)
            continue

        formatted_parts.append(f"<p>{line}</p>")  # ✅ 通常の説明
        

    final_output = "\n".join(formatted_parts).lstrip("\n")  # ✅ 先頭の余分な改行を削除
    final_output = re.sub(r"(<pre><code>)\n+", r"\1", final_output)

    return final_output



def format_description(description):
    lines = description.split("\n")
    formatted_parts = []
    table_buffer = []  # ✅ 表のデータを一時保存するバッファ
    in_code_block = False  # ✅ コードブロックの判定フラグ
    in_table = False  # ✅ 表の判定フラグ

    for line in lines: 
        stripped_line = line.strip()
        
            # ✅ **コードブロックの開始・終了**
        if stripped_line.startswith("<pre><code>"):
            in_code_block = True
            code_buffer = [line]  # ✅ `<pre><code>` の開始タグだけ保存
            
            continue

        # ✅ **コードブロックの終了**
        elif stripped_line.startswith("</code></pre>"):
            in_code_block = False
            code_buffer.append(line)  # ✅ `</code></pre>` の終了タグも保存
            cleaned_code = "\n".join(code_buffer).lstrip("\n") #最初の行以外は冒頭に改行をつける。
            
            formatted_parts.append(cleaned_code)  # ✅ `code_buffer` を1つの `<pre><code>` にまとめる
            
            code_buffer = []  # ✅ バッファをリセット
            
            continue

        # ✅ **コードブロック内なら `code_buffer` に追加**
        if in_code_block:
            code_buffer.append(line)
            
            continue  # ✅ 他の処理をスキップ
        
        if "\t" in stripped_line:  # ✅ タブがある場合 → 表の処理
            clean_line = re.sub(r"</?p>", "", line)  # ✅ <p> タグを削除！

            if not in_table:  # ✅ 表の開始
                formatted_parts.append("<table class='custom-table'>")
                in_table = True

            formatted_line = clean_line.replace('\t', '</td><td>')
            formatted_parts.append(f"<tr><td>{formatted_line}</td></tr>")
            continue

        else:  # ✅ **通常のテキスト処理**
            if in_table:  # ✅ 表の終了
                formatted_parts.append("</table>")
                in_table = False

        
            # ✅ **ここが重要！`<p>` の扱いを整理**
        if stripped_line.startswith("<p>") and stripped_line.endswith("</p>"):
            
            
            formatted_parts.append(line)
        elif stripped_line:  
            formatted_parts.append(f"<p>{line}</p>")
        else:
            formatted_parts.append("<p>&nbsp;</p>")
            
    # ✅ **最後に `in_table` が `True` のままなら閉じる**
    if in_table:
        formatted_parts.append("</table>")

    return Markup("\n".join(formatted_parts))  # ✅ 最後に `Markup` を適用

@app.route('/')
def home():
    print("🔥 home() が呼ばれました！", file=sys.stderr)

    # ✅ カテゴリ・難易度のリストを取得
    categories = db.session.query(Category).all()
    difficulty_levels = db.session.query(DifficultyLevel).all()

    return render_template(
        'top.html',
        categories=categories,
        difficulty_levels=difficulty_levels
    )

    # ✅ カテゴリ・難易度のリストを取得
    categories = db.session.query(Category).all()
    difficulty_levels = db.session.query(DifficultyLevel).all()


@app.route('/question/<int:id>', methods=['GET'])
@app.route('/questions', methods=['GET'])
def view_question(id=None):
    print(f"🔥 view_question() が呼ばれました！ ID={id}", file=sys.stderr)

    # ✅ リクエストされた `id` を取得（int型）
    current_id = id
    
    # ✅ フィルタ条件を取得
    category_id = request.args.get("category_id", default=None, type=int)
    difficulty_level_id = request.args.get("difficulty_level_id", default=None, type=int)
    query = request.args.get("q", default=None)

    # ✅ カテゴリ・難易度のリストを取得（HTML用）
    categories = db.session.query(Category).all()
    difficulty_levels = db.session.query(DifficultyLevel).all()

    # ✅ `query_filter` を作成（ここで全体の問題数と順位を計算）
    query_filter = (
        db.session.query(
            Question,
            Category.name.label("category_name"),
            DifficultyLevel.level.label("difficulty_name"),
            db.func.count().over().label("total_questions"),
            db.func.rank().over(order_by=Question.id).label("question_number"),
        )
        .join(Category, Question.category_id == Category.id)
        .join(DifficultyLevel, Question.difficulty_id == DifficultyLevel.id)
    )

    

    # ✅ フィルタ適用（カテゴリ・難易度・検索キーワード）
    if category_id:
        query_filter = query_filter.filter(Question.category_id == category_id)
    if difficulty_level_id:
        query_filter = query_filter.filter(Question.difficulty_id == difficulty_level_id)
    if query:
        query_filter = query_filter.filter(Question.question.ilike(f"%{query}%"))

    # ✅ `current_id` が `None` の場合は最初の問題を取得
    if current_id is None:
        first_question = query_filter.order_by(Question.id.asc()).first()
        current_id = first_question.Question.id if first_question else None

    
 
    # ✅ `total_questions` をサブクエリで取得
    total_questions_query = db.session.query(db.func.count()).select_from(Question)

    if category_id:
        total_questions_query = total_questions_query.filter(Question.category_id == category_id)
    if difficulty_level_id:
        total_questions_query = total_questions_query.filter(Question.difficulty_id == difficulty_level_id)

    total_questions = total_questions_query.scalar() or 1  # ✅ None の場合 1 にする





    # ✅ `question_number` を取得
    question_number_query = (
        db.session.query(db.func.count())
        .filter(Question.id <= current_id)
    )

    if category_id:
        question_number_query = question_number_query.filter(Question.category_id == category_id)
    if difficulty_level_id:
        question_number_query = question_number_query.filter(Question.difficulty_id == difficulty_level_id)

    question_number = question_number_query.scalar() or 1  # ✅ None の場合 1 にする

    
    # ✅ `current_id` に該当する問題を取得
    question = query_filter.filter(Question.id == current_id).first()
    
    # ✅ `question` が取得できない場合はリダイレクト
    if not question:
        flash("🚨 検索結果がありません。別のキーワードで試してください。", "warning")
        return redirect(url_for("view_questions"))
    
    # ✅ `question` を展開（_mapping を使用）
    
    question_data = question._mapping["Question"]
    category_name = question._mapping["category_name"]
    difficulty_name = question._mapping["difficulty_name"]
    
        # ✅ `question_data` の `question` と `description` に `detect_code_blocks()` と `format_description()` を適用
    if hasattr(question_data, "question") and question_data.question is not None:
        question_data.question = detect_code_blocks(question_data.question)
        question_data.question = format_description(question_data.question)
    
    if hasattr(question_data, "answer") and question_data.answer is not None:
        question_data.answer = detect_code_blocks(question_data.answer)
        question_data.answer = format_description(question_data.answer)


    if hasattr(question_data, "description") and question_data.description is not None:
        question_data.description = detect_code_blocks(question_data.description)
        question_data.description = format_description(question_data.description)

    

    # ✅ 「次の問題」と「前の問題」を取得
    next_question = (
        query_filter.filter(Question.id > current_id)
        .order_by(Question.id.asc())
        .first()
    )
    
    prev_question = (
        query_filter.filter(Question.id < current_id)
        .order_by(Question.id.desc())
        .first()
    )

    next_id = next_question.Question.id if next_question else None
    prev_id = prev_question.Question.id if prev_question else None
    
    # ✅ 検索結果の最初・最後の問題の ID を取得
    first_question = query_filter.with_entities(Question.id).order_by(Question.id.asc()).first()
    last_question = query_filter.with_entities(Question.id).order_by(Question.id.desc()).first()

    # ✅ `None` だった場合のデフォルト値を設定
    first_question_id = first_question[0] if first_question else 1
    last_question_id = last_question[0] if last_question else 1




    

    # ✅ 取得したデータをテンプレートに渡す
    return render_template(
        'question.html',
        questions=[question_data],
        categories=categories,
        category_id=category_id,
        question=question_data,
        current_id=current_id,
        next_id=next_id,
        prev_id=prev_id,
        query=query,
        difficulty_levels=difficulty_levels,
        difficulty_level_id=difficulty_level_id,
        total_questions=total_questions,
        question_number=question_number,
        first_question_id=first_question_id,
        last_question_id = last_question_id
    )






# 問題登録用ルート
@app.route('/admin/add', methods=['GET', 'POST'])
@admin_required  # ✅ これを追加！
def add_question():
    if request.method == 'POST':


        question_text = request.form['question']
        answer = request.form['answer']
        description = request.form.get('description', '')
        category_id = request.form.get('category_id', None)
        difficulty_id = request.form.get('difficulty_id', None)

 
        if not question_text or not answer:
            print("❌ エラー: question または answer が空です！")
            return "Bad Request: 必須項目が空です", 400  # ここで明示的にエラーを返す

        try:
            new_question = Question(
                question=question_text,
                answer=answer,
                description=description,
                category_id=int(category_id) if category_id else None,
                difficulty_id=int(difficulty_id) if difficulty_id else None
            )

            db.session.add(new_question)
            db.session.commit()

            return redirect(url_for('manage_questions'))

        except IntegrityError as e:
            db.session.rollback()  # 💡 エラーが起きたらロールバック
            return jsonify({"error": "データベース制約違反が発生しました！"}), 500

        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "サーバー内部エラーが発生しました！"}), 500

    categories = db.session.query(Category).all()
    difficulty_levels = db.session.query(DifficultyLevel).all()

    return render_template('add_question.html', categories=categories, difficulty_levels=difficulty_levels)


# 管理画面（削除ボタン含む）
@app.route('/admin/manage', methods=['GET', 'POST'])
@admin_required 
def manage_questions():
    questions = (
        db.session.query(
            Question.id,
            Question.question,
            Category.name.label("category_name"),
            DifficultyLevel.level.label("difficulty_name"),
        )
        .outerjoin(Category, Question.category_id == Category.id)
        .outerjoin(DifficultyLevel, Question.difficulty_id == DifficultyLevel.id)
        .order_by(Question.id.asc())  # ✅ `.order_by()` を適切な位置に
        .all()  # ✅ `.all()` も正しく適用
    )

    
    return render_template('manage_questions.html', questions=questions)

# 削除用ルート
@app.route('/admin/delete/<int:question_id>', methods=['POST'])
@admin_required
def delete_question(question_id):
    try:
        with app.app_context():  # ✅ Flask のアプリコンテキストを設定
            question = db.session.get(Question, question_id)  # ✅ `query.get()` → `db.session.get()` に変更
            
            if not question:
                return jsonify({"error": "編集する問題が見つかりません！"}), 404

            db.session.delete(question)
            db.session.commit()
            db.session.remove()  # ✅ セッションを明示的に閉じる
   

            # ✅ `redirect()` を使って、最新の管理画面にリダイレクト！
            return redirect(url_for('manage_questions'))

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "削除に失敗しました！"}), 500




# 問題編集用ルート
@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_question(id):
    # ✅ IDが正しく取得されているか確認
    try:
        id = int(id)  # IDが整数であることを保証

    except ValueError:
        print(f"🚨 IDが整数ではありません！ ID={id}", file=sys.stderr)
        return jsonify({"error": "IDが無効です！"}), 400

    # ✅ データベースから該当の問題を取得
    question = db.session.query(Question).filter_by(id=id).first()

    if not question:
        print(f"🚨 問題が見つかりません！ ID={id}", file=sys.stderr)
        return jsonify({"error": "編集する問題が見つかりません！"}), 400

    # ✅ `GET` の場合（編集画面を表示）
    if request.method == 'GET':
        categories = db.session.query(Category).all() or []
        difficulty_levels = db.session.query(DifficultyLevel).all() or []

        return render_template('edit_question.html', question=question, categories=categories, difficulty_levels=difficulty_levels)

    # ✅ `POST` の場合（データを更新）
    if request.method == 'POST':

        try:
            data = request.get_json()


            if not data:
                print(f"🚨 受け取ったデータが `None` です！", file=sys.stderr)
                return jsonify({"error": "リクエストボディが JSON 形式ではありません！"}), 400

            # ✅ データを更新
            question.question = data.get("question")
            question.answer = data.get("answer")
            question.description = data.get("description", "")
            question.category_id = int(data.get("category_id", 0)) or None
            question.difficulty_level_id = int(data.get("difficulty_level_id", 0)) or None

            db.session.commit()


            print(f"✅ 「問題を更新しました！」を返します！", file=sys.stderr)
            return jsonify({"message": "問題を更新しました！"}), 200

        except Exception as e:
            db.session.rollback()

            print(f"🚨 データ更新エラー: {e}", file=sys.stderr)
            return jsonify({"error": f"エラー: {e}"}), 500


@app.route("/admin/edit_all")
@admin_required
def show_questions():
    # ✅ 問題一覧を取得（カテゴリ名・難易度名を含める）
    questions = db.session.execute(text("""
        SELECT 
            q.id, q.question, q.answer, q.description, 
            q.category_id, c.name AS category_name,
            q.difficulty_id, d.level AS difficulty_level
        FROM public.questions q
        LEFT JOIN public.categories c ON q.category_id = c.id
        LEFT JOIN public.difficulty_levels d ON q.difficulty_id = d.id
    """)).fetchall()

    # ✅ カテゴリ一覧を取得
    categories = db.session.execute(text("SELECT id, name FROM public.categories")).fetchall()

    # ✅ 難易度一覧を取得
    difficulty_levels = db.session.execute(text("SELECT id, level FROM public.difficulty_levels")).fetchall()
    return render_template("edit_all.html", questions=questions, categories=categories, difficulty_levels=difficulty_levels)

#edit_allでの保存
@app.route("/admin/edit/<int:id>", methods=["POST"])
def update_question(id):
    data = request.json  # ✅ JavaScript から送られてきたデータを取得

    # ✅ `id` に対応する `question` を取得
    question = db.session.execute(text("""
        SELECT * FROM public.questions WHERE id = :id
    """), {"id": id}).fetchone()

    # ✅ デバッグ: question がちゃんと取得できているか確認
    print("デバッグ: question = ", question)

    if question is None:
        return jsonify({"error": "Question not found"}), 404  # ❌ IDが存在しない場合のエラー処理

    # ✅ データをデバッグ表示
    print("受け取ったデータ:", data)

    # ✅ データベースの `questions` テーブルを更新
    db.session.execute(text("""
        UPDATE public.questions
        SET 
            question = :question,
            answer = :answer,
            description = :description,
            category_id = :category_id,
            difficulty_id = :difficulty_level_id
        WHERE id = :id
    """), {
        "question": data["question"],
        "answer": data["answer"],
        "description": data["description"],
        "category_id": data["category_id"],
        "difficulty_level_id": data["difficulty_level_id"],
        "id": id
    })

    db.session.commit()  # ✅ データを確定
    return jsonify({"message": "更新成功！"})  # ✅ 成功メッセージを返す



if sys.platform != "win32":
    import resource
#禁止モジュールのフィルタリング
FORBIDDEN_KEYWORDS = ["import os", "import sys", "import subprocess", "import multiprocessing"]

def is_safe_code(code):
    return not any(keyword in code for keyword in FORBIDDEN_KEYWORDS)

def set_limits():
    """CPU時間とメモリ使用量を制限"""
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))  # CPU時間を2秒に制限
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))  # メモリを256MBに制限

#コード入力用
@app.route('/run', methods=['POST'])
def run_code():
    data = request.json
    code = data.get("code", "")

    if not is_safe_code(code):
        return jsonify({"result": "⚠️ 禁止されたコードが含まれています。"})

    try:
        if sys.platform != "win32":  # **Linux環境のみ制限を適用**
            result = subprocess.run(
                ["python", "-c", f"import resource; resource.setrlimit(resource.RLIMIT_CPU, (2, 2)); {code}"],
                capture_output=True, text=True, timeout=3
            )
        else:  # **Windowsでは普通に実行（制限なし）**
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True, text=True, timeout=3
            )

        output = result.stdout if result.stdout else result.stderr

    except subprocess.TimeoutExpired:
        output = "⚠️ 実行時間が長すぎます！"
    except MemoryError:
        output = "⚠️ メモリ使用量が多すぎます！"
    except Exception as e:
        output = str(e)

    return jsonify({"result": output})

@app.route('/disclaimer')
def disclaimer():
    # Markdownファイルを読み込む
    with open("disclaimer.md", "r", encoding="utf-8") as f:
        md_content = f.read()

    # MarkdownをHTMLに変換
    html_content = markdown.markdown(md_content)

    return render_template("disclaimer.html", content=Markup(html_content))





@app.errorhandler(500)
def internal_error(error):
    print(f"🚨 500 Internal Server Error: {error}", file=sys.stderr)
    traceback.print_exc()  # ✅ 詳細なエラーログを表示！
    return jsonify({"error": "サーバー内部エラーが発生しました！"}), 500


# アプリ起動

DEBUG_MODE = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # ✅ `PORT` を取得
    app.run(host="0.0.0.0", port=port, debug=DEBUG_MODE)  # ✅ `FLASK_DEBUG` でデバッグモードを制御！