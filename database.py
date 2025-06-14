import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, inspect
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# アプリケーションのサポートディレクトリにDBファイルを作成
app_support_dir = os.path.expanduser('~/Library/Application Support/OpenSuperWhisperPy')
os.makedirs(app_support_dir, exist_ok=True)
db_path = os.path.join(app_support_dir, 'recordings.sqlite')
engine = create_engine(f'sqlite:///{db_path}')

# セッションを作成
Session = sessionmaker(bind=engine)
session = Session()

# モデルのベースクラス
Base = declarative_base()

class Recording(Base):
    __tablename__ = 'recordings'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    file_path = Column(String, nullable=False)
    transcription = Column(String, nullable=False)
    duration = Column(Float, nullable=False)

    def __repr__(self):
        return f"<Recording(timestamp='{self.timestamp}', transcription='{self.transcription[:20]}...')>"

# テーブルが存在しない場合は作成する
inspector = inspect(engine)
if not inspector.has_table("recordings"):
    Base.metadata.create_all(engine)

# 録音データを追加する関数の例
def add_recording(file_path, transcription, duration):
    new_recording = Recording(
        file_path=file_path,
        transcription=transcription,
        duration=duration
    )
    session.add(new_recording)
    session.commit()
    return new_recording

# 全ての録音データを取得する関数の例
def get_all_recordings():
    return session.query(Recording).order_by(Recording.timestamp.desc()).all()