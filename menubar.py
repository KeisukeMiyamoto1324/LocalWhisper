# menubar.py (アプリケーションのメインファイルとして機能)

import rumps
import threading
import os
from main_background import BackgroundRecorder

# このファイルの場所を基準にアイコンへのパスを生成
# これにより、どこから実行してもアイコンを正しく読み込める
try:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    APP_DIR = os.getcwd() # インタラクティブシェルなどで__file__がない場合へのフォールバック

ICON_DEFAULT = os.path.join(APP_DIR, 'icon_default.png')
ICON_RECORDING = os.path.join(APP_DIR, 'icon_recording.png')

class WhisperMenuBarApp(rumps.App):
    def __init__(self):
        # rumps.Appを初期化。初期アイコンを指定。
        super(WhisperMenuBarApp, self).__init__("LocalWhisper", icon=ICON_DEFAULT)
        
        # メニューバーに表示される項目を設定
        self.menu = [
            rumps.MenuItem('Quit', callback=self.quit_app)
        ]
        
        # BackgroundRecorderを初期化
        # アイコンを更新するメソッドをコールバックとして渡す
        self.background_recorder = BackgroundRecorder(status_update_callback=self.update_icon_status)
        
        # キーボードリスナーを別スレッドで開始
        self.listener_thread = threading.Thread(target=self.background_recorder.start_listener)
        self.listener_thread.daemon = True  # メインアプリ終了時にこのスレッドも自動で閉じる
        self.listener_thread.start()

    def update_icon_status(self, is_recording: bool):
        """
        BackgroundRecorderからのコールバックで呼び出されるメソッド。
        録音状態に応じてメニューバーのアイコンを切り替える。
        """
        if is_recording:
            self.icon = ICON_RECORDING
            print("UI: Icon updated to 'recording'.")
        else:
            self.icon = ICON_DEFAULT
            print("UI: Icon updated to 'default'.")

    def quit_app(self, _):
        """アプリケーションを終了する"""
        print("Quitting application...")
        # バックグラウンドのリスナーを安全に停止
        self.background_recorder.stop_listener()
        rumps.quit_application()

if __name__ == '__main__':
    # 実行前にアイコンファイルの存在を確認
    if not os.path.exists(ICON_DEFAULT) or not os.path.exists(ICON_RECORDING):
        # rumpsはアイコンがないとエラーで起動しないため、ここでチェックする
        rumps.alert(
            title="エラー",
            message=f"アイコンファイルが見つかりません。\n'{ICON_DEFAULT}'\n'{ICON_RECORDING}'\nがアプリケーションと同じディレクトリにあることを確認してください。"
        )
    else:
        # アプリケーションインスタンスを作成し、実行
        app = WhisperMenuBarApp()
        app.run()