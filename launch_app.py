import os
import sys
import webbrowser
import threading
import time
from pathlib import Path

if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, application_path)

os.chdir(application_path)

data_dir = Path(application_path) / 'data'
data_dir.mkdir(exist_ok=True)
(data_dir / 'uploads').mkdir(exist_ok=True)
(data_dir / 'output').mkdir(exist_ok=True)


def open_browser():
    """延迟打开浏览器"""
    time.sleep(2) 
    webbrowser.open('http://127.0.0.1:8080')

def main():
    """主函数"""
    try:
        # 在后台线程中打开浏览器
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        # 导入并启动Flask应用
        from app import app, logger
        
        logger.info("Runing ScholarMind Web")
        
        # 启动Flask应用（不显示调试信息）
        app.run(host='127.0.0.1', port=8080, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        print("\n应用程序已停止")
    except Exception as e:
        print(f"启动应用程序时出错: {e}")
        input("按回车键退出...")

if __name__ == '__main__':
    main()