from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()  

class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    difficulty_id = db.Column(db.Integer, db.ForeignKey("difficulty_levels.id"), nullable=True)

    __table_args__ = {"extend_existing": True}

class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)

    questions = db.relationship("Question", backref="category", lazy=True)

    __table_args__ = {"extend_existing": True}

class DifficultyLevel(db.Model):
    __tablename__ = "difficulty_levels"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    level = db.Column(db.String(255), nullable=False)

    questions = db.relationship("Question", backref="difficulty", lazy=True)

    __table_args__ = {"extend_existing": True}
