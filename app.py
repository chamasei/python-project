from flask import Flask, request, render_template, redirect, url_for, flash,jsonify
from markupsafe import Markup
import subprocess
import sqlite3
import logging
import sys
import re

# ログ設定
logging.basicConfig(
    filename="execution.log",         # ログファイル名
    level=logging.INFO,               # ログレベル
    format="%(asctime)s - %(levelname)s - %(message)s"  # フォーマット
)

app = Flask(__name__)
app.secret_key = "your_secret_key"  # フラッシュメッセージに必要



# データベース接続
def get_db_connection():
    conn = sqlite3.connect('questions.db')
    conn.row_factory = sqlite3.Row
    return conn


def format_description(description):
    """
    解説のテキストをHTMLに適切に変換する
    - タブ区切りの行だけを `<table>` に変換
    - 通常の文章は `<p>` に保持し、改行は `<br>` に変換
    - 空行 (`\n\n`) は `<p>` の区切りとして扱う
    """
    lines = description.strip().split("\n")
    formatted_parts = []
    table_buffer = []
    paragraph_buffer = []

    for line in lines:
        if "\t" in line:  # タブ区切りなら表データとして処理
            # 直前に段落があれば閉じる
            if not table_buffer:
                table_buffer.append("<table class='custom-table' border='1' style='border-collapse: collapse;'>")
            table_buffer.append("<tr>" + "".join(f"<td style='padding:5px;'>{cell}</td>" for cell in line.split("\t")) + "</tr>")
        else:
            # ✅ もし table_buffer にデータがあるなら、ここで <table> を閉じる
            if table_buffer:
                table_buffer.append("</table>")
                formatted_parts.append("".join(table_buffer))  # ✅ 1つの表として追加
                table_buffer = []  # ✅ ここでリセット！

            # 通常の段落処理 
            if line.strip() == "" and paragraph_buffer:
                formatted_parts.append("<p>" + "<br>".join(paragraph_buffer) + "</p>")
                paragraph_buffer = []
            else:
                paragraph_buffer.append(line.replace(" ", "&nbsp;"))

    # ✅ もし最後の部分で table_buffer にデータが残っていたら閉じる
    if table_buffer:
        table_buffer.append("</table>")
        formatted_parts.append("".join(table_buffer))

        

    if paragraph_buffer:
        formatted_parts.append("<p>" + "<br>".join(paragraph_buffer) + "</p>")
        paragraph_buffer = []


    return Markup("\n".join(formatted_parts))
    


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

    # `view_questions()` で `description` に適用
    #print("Before applying format_description:", question['description']) 
    question['description'] = format_description(question['description']) if question and 'description' in question else "（解説なし）"
    #print("After applying format_description:", question['description'])

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
    
    print("🔎 query:", query)   
    
    
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







#コード入力用
@app.route('/run', methods=['POST'])
def run_code():
    data = request.json
    code = data.get("code", "")

    try:
        # セキュリティ対策のため、subprocess で実行
        result = subprocess.run(
            ["python", "-c", code],  # コードを実行
            capture_output=True, text=True, timeout=3  # タイムアウトを 3 秒に設定
        )
        output = result.stdout if result.stdout else result.stderr  # エラーがあれば stderr を表示
    except Exception as e:
        output = str(e)


    return jsonify({"result": output})  # JSON で結果を返す






# アプリ起動

if __name__ == "__main__":
    app.run(debug=True, extra_files=["templates/index.html", "static/style.css"])
