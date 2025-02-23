from flask import Flask, request, session,render_template, redirect, url_for, flash,jsonify
from markupsafe import Markup
import subprocess
import sqlite3
import logging
import sys
import re
from dotenv import load_dotenv
import os
from functools import wraps  # ✅ これを追加！

load_dotenv()

# ログ設定
logging.basicConfig(
    filename="execution.log",         # ログファイル名
    level=logging.DEBUG,               # ログレベル
    format="%(asctime)s - %(levelname)s - %(message)s"  # フォーマット
)

app = Flask(__name__)

#管理者用
# ✅ 環境変数から secret_key を取得（設定がなければ "your_secret_key_here" を使う）
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your_secret_key_here") 
ADMIN_PASSWORD = os.getenv("PYTHON_ADMIN_PASSWORD")

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
            return redirect(url_for('manage_questions'))
        else:
            flash("⚠️ パスワードが違います。", "error")
        

    return render_template('admin_login.html')


@admin_required
def manage_questions():
    conn = get_db_connection()
    questions = conn.execute('''
        SELECT questions.id, questions.question, categories.name AS category_name, difficulty_levels.name AS difficulty_name
        FROM questions
        LEFT JOIN categories ON questions.category_id = categories.id
        LEFT JOIN difficulty_levels ON questions.difficulty_id = difficulty_levels.id
    ''').fetchall()
    conn.close()
    return render_template('manage_questions.html', questions=questions)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("✅ ログアウトしました。", "success")
    return redirect(url_for('admin_login'))


# データベース接続
def get_db_connection():
    conn = sqlite3.connect('questions.db')
    conn.row_factory = sqlite3.Row
    return conn








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

            formatted_parts.append(f"<tr><td>{clean_line.replace('\t', '</td><td>')}</td></tr>")  # ✅ `<td>` に変換
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



@app.route('/', methods=['GET'])

def view_questions():
    print("🔥 view_questions() が呼ばれました！", file=sys.stderr) 
    conn = get_db_connection()

    # 選択されたカテゴリを取得（デフォルトはすべて）
    category_id = request.args.get('category_id') 
    query = request.args.get('q')  # ✅ キーワード検索   
    difficulty_level_id = request.args.get('difficulty_level_id')

    # ✅ `difficulty_level_id` が `None` の場合を考慮し、`str` のみ `int` に変換！
    if difficulty_level_id is not None and difficulty_level_id.isdigit():
        difficulty_level_id = int(difficulty_level_id)
    else:
        difficulty_level_id = None  # ✅ `None` を維持する！
    
    
    # カテゴリ一覧を取得
    categories = conn.execute("SELECT * FROM categories").fetchall()
    difficulty_levels = conn.execute("SELECT * FROM difficulty_levels").fetchall()

    # ✅ 初回アクセス時に `None` なら適切なデフォルト値を設定
    if category_id is None:
        category_id = ""  # ✅ すべてのカテゴリを対象にする
    if difficulty_level_id is None:
        difficulty_level_id = ""  # ✅ すべての難易度を対象にする


    # リクエストされた URL の id を取得する処理
    current_id = request.args.get('id')


    if not current_id:
        current_id = conn.execute('SELECT MIN(id) FROM questions').fetchone()[0]




    # ✅ `WHERE` 句の条件を動的に組み立てる
    conditions = []
    params = []    

    if category_id and category_id.isdigit():
        conditions.append("category_id = ?")
        params.append(int(category_id))
    

    if difficulty_level_id :
        conditions.append("difficulty_id = ?")
        params.append(int(difficulty_level_id))

    if query:
        conditions.append("(question LIKE ? OR answer LIKE ?)")
        params.append(f"%{query}%")
        params.append(f"%{query}%")


    where_clause = " AND ".join(conditions) if conditions else "1=1"  # ✅ 条件がない場合は `1=1`

    if category_id or difficulty_level_id or query:  # ✅ 検索条件が指定された場合
        first_question = conn.execute(f'''
            SELECT id FROM questions WHERE {where_clause} ORDER BY id ASC LIMIT 1
        ''', params).fetchone()
        
        #  `id` がない（最初の検索実行時のみ） or `id=1` のときのみ適用！
        if first_question and (current_id is None or current_id == 1):  
            current_id = first_question[0]  # ✅ 検索結果の1問目を取得！

 
    #  フィルタリングされた問題を取得
    params_for_query = [current_id] + params if "?" in where_clause else [current_id]
    sql = f"""
        SELECT questions.*,
            categories.name AS category_name,
            difficulty_levels.name AS difficulty_name
        FROM questions
        LEFT JOIN categories ON questions.category_id = categories.id
        LEFT JOIN difficulty_levels ON questions.difficulty_id = difficulty_levels.id
        WHERE questions.id = ? AND {where_clause} ORDER BY id ASC
    """
    question = conn.execute(sql, params_for_query).fetchone()


    if question:
        question = dict(question)

    #  `next_id` の取得
    sql_next = f"SELECT MIN(id) FROM questions WHERE id > ? AND {where_clause} AND id != ? ORDER BY id ASC"


    next_id_row = conn.execute(sql_next, [current_id] + params + [current_id]).fetchone()
    next_id = next_id_row[0] if next_id_row and next_id_row[0] is not None else None


    if question:
        if 'question' in question and question['question'] is not None:
            question['question'] = detect_code_blocks(question['question'])
            question['question'] = format_description(question['question'])

        if 'description' in question and question['description'] is not None:
            question['description'] = detect_code_blocks(question['description'])
            question['description'] = format_description(question['description'])
        if question is None:
            flash("🚨 検索結果がありません。別のキーワードで試してください。", "warning")
            return redirect(url_for("index"))  # 🔄 検索ページにリダイレクト
    else:
        print("🚨 DEBUG: `question` is None! 検索結果がありません。")
        

    if question:
        question = dict(question)  #  `sqlite3.Row` を `dict` に変換

        #  `None` の場合は適切なデフォルト値をセット
        question['question'] = question['question'] if question['question'] else "（問題なし）"
        question['answer'] = question['answer'] if question['answer'] else "（答えなし）"
        question['description'] = question['description'] if question['description'] else "（解説なし）"
        question['expected_output'] = question['expected_output'] if question['expected_output'] else "（出力例なし）"

        #  `category_id` と `difficulty_id` は `None` のままにする（数値 or None）
        question['category_id'] = question['category_id'] if question['category_id'] is not None else None
        question['difficulty_id'] = question['difficulty_id'] if question['difficulty_id'] is not None else None
    

    # 「前の問題」の取得も修正    
    max_id = conn.execute('SELECT MAX(id) FROM questions').fetchone()[0] # 問題IDの最大値・最小値を取得

    if category_id:
        prev_id = conn.execute('''
            SELECT MAX(id) FROM questions WHERE id < ? AND category_id = ?
        ''', (current_id, category_id)).fetchone()
    else:
        prev_id = conn.execute('''
            SELECT MAX(id) FROM questions WHERE id < ?
        ''', (current_id,)).fetchone()

    if prev_id and prev_id[0] is not None:
        prev_id = prev_id[0]
    else:
        if category_id:
            flash("このカテゴリの最初の問題です。", "info")
            prev_id = None  # その場にとどまる
        else:
            prev_id = max_id  # すべてのカテゴリで前の問題がない場合は最後に戻る

    if category_id or difficulty_level_id or query:
        total_questions_row = conn.execute(f"SELECT COUNT(*) FROM questions WHERE {where_clause}", params).fetchone()
    else:
        total_questions_row = conn.execute("SELECT COUNT(*) FROM questions").fetchone()
        
    total_questions = total_questions_row[0] if total_questions_row and total_questions_row[0] is not None else 0

    question_position_row = conn.execute(f"SELECT COUNT(*) FROM questions WHERE id < ? AND {where_clause}", [current_id] + params).fetchone()
    question_number = question_position_row[0] + 1 if question_position_row else 1


    conn.close()
    if not question:
        flash("問題が見つかりません。", "error")
        return redirect(url_for('view_questions'))
    
    
    
    return render_template(
        'index.html', 
        questions=[question],
        categories=categories, 
        category_id=category_id, 
        question=question, 
        current_id=current_id,                 
        next_id=next_id, 
        prev_id=prev_id,
        query = query, 
        difficulty_levels=difficulty_levels,
        difficulty_level_id = difficulty_level_id,
        total_questions = total_questions,
        question_number = question_number,

    )
    





# 問題登録用ルート
@app.route('/admin/add', methods=['GET', 'POST'])
@admin_required  # ✅ これを追加！
def add_question():
    conn = get_db_connection()

    # カテゴリと難易度のリストを取得
    categories = conn.execute("SELECT * FROM categories").fetchall()
    difficulty_levels = conn.execute("SELECT * FROM difficulty_levels").fetchall()

    if request.method == 'POST':
        question = request.form.get('register_question')
        answer = request.form.get('register_answer')
        description = request.form.get('register_description') 
        category_id = request.form.get("category_id")
        difficulty_id = request.form.get("difficulty_id")

        if question and answer and description and category_id and difficulty_id:
            conn.execute('INSERT INTO questions (question, answer,description, category_id, difficulty_id) VALUES (?, ?, ?, ?, ?)',
                          (question, answer,description, category_id, difficulty_id)
                          )
            conn.commit()
            conn.close()
            flash("問題が登録されました！", "success")
        else:
            flash("すべてのフィールドを入力してください。", "error")

        return redirect(url_for('add_question'))
       
  
    return render_template('add_question.html', categories=categories, difficulty_levels=difficulty_levels)



# 管理画面（削除ボタン含む）
@app.route('/admin/manage', methods=['GET', 'POST'])
@admin_required 
def manage_questions():
    conn = get_db_connection()
    
    questions = conn.execute('''
        SELECT questions.id, questions.question, categories.name AS category_name, difficulty_levels.name AS difficulty_name
        FROM questions
        LEFT JOIN categories ON questions.category_id = categories.id
        LEFT JOIN difficulty_levels ON questions.difficulty_id = difficulty_levels.id
    ''').fetchall()
    
    conn.close()
    return render_template('manage_questions.html', questions=questions,question =questions)


# 削除用ルート
@app.route('/delete/<int:id>', methods=['POST'])
def delete_question(id):
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM questions WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        flash("問題が削除されました！", "success")
    except Exception as e:
        print(f"Error: {e}")
        flash("削除中にエラーが発生しました。", "error")
    return redirect(url_for('manage_questions'))


# 問題編集用ルート
@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@admin_required 
def edit_question(id):
    conn = get_db_connection()

    if request.method == 'POST':  # ✅ `POST` の処理！
        # ✅ `JSON` データを受け取る（form ではなく JSON）
        data = request.get_json()  # ← ここが重要！
        
        question_text = data.get('question', "").strip()  # ✅ `None` にならないように `""` をデフォルト値に
        answer = data.get('answer', "").strip()
        description = data.get('description', "").strip()
        category_id = data.get('category_id')
        difficulty_level_id = data.get('difficulty_level_id')

        # ✅ `category_id` や `difficulty_level_id` を `int` に変換
        category_id = int(category_id) if category_id and isinstance(category_id, str) and category_id.isdigit() else None
        difficulty_level_id = int(difficulty_level_id) if difficulty_level_id and isinstance(difficulty_level_id, str) and difficulty_level_id.isdigit() else None

        # ✅ データベースを更新
        conn.execute("""
            UPDATE questions 
            SET question = ?, answer = ?, description = ?, category_id = ?, difficulty_id = ? 
            WHERE id = ?
        """, (question_text, answer, description, category_id, difficulty_level_id, id))

        conn.commit()
        conn.close()

        flash("問題が更新されました！", "success")
        return jsonify({"message": "更新成功"})  
    
    # ✅ `GET` の処理（編集ページを表示）
    question = conn.execute("""
        SELECT questions.*, categories.name AS category_name, difficulty_levels.name AS difficulty_name 
        FROM questions
        LEFT JOIN categories ON questions.category_id = categories.id
        LEFT JOIN difficulty_levels ON questions.difficulty_id = difficulty_levels.id
        WHERE questions.id = ?
    """, (id,)).fetchone()
    
    categories = conn.execute("SELECT * FROM categories").fetchall()
    difficulty_levels = conn.execute("SELECT * FROM difficulty_levels").fetchall()
    conn.close()

    if question is None:
        flash("問題が見つかりません。", "error")
        return redirect(url_for('manage_questions'))

    return render_template("edit_question.html", question=question, categories=categories, difficulty_levels=difficulty_levels)


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




@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500


# アプリ起動

if __name__ == "__main__":
    app.run(debug=True)
