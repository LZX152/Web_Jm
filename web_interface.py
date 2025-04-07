from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory
import os
import yaml
import threading
import jmcomic
from jmcomic import DirRule
import uuid
from urllib.parse import quote
from difflib import SequenceMatcher
from fuzzywuzzy import fuzz
from pathlib import Path
from datetime import datetime
app = Flask(__name__)


# HTML模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>JM漫画下载器</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
        }
        input[type="text"] {
            width: 100%;
            padding: 8px;
            box-sizing: border-box;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            cursor: pointer;
        }
        button:hover {
            background-color: #45a049;
        }
        .status {
            margin-top: 20px;
        }
        .task {
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .completed {
            background-color: #e8f5e9;
        }
        .in-progress {
            background-color: #fff9c4;
        }
        .failed {
            background-color: #ffebee;
        }
    </style>
    <script>
        // 添加自动刷新功能
        function checkForInProgressTasks() {
            const tasks = document.querySelectorAll('.task.in-progress');
            if (tasks.length > 0) {
                // 如果有正在进行的任务，5秒后刷新页面
                setTimeout(() => {
                    window.location.reload();
                }, 5000);
            }
        }
        
        // 页面加载完成后执行
        window.onload = function() {
            checkForInProgressTasks();
        };
    </script>
</head>
<body>
    <h1>JM漫画下载器</h1>
    
    <!-- 添加查看文件列表按钮 -->
    <div style="margin-bottom: 20px;">
        <button onclick="showPdfList()" style="background-color: #4CAF50; color: white; padding: 10px 15px; border: none; cursor: pointer;">
            查看PDF文件列表
        </button>
    </div>
    
    <!-- 添加用于显示文件列表的div -->
    <div id="pdfList" style="margin-bottom: 20px;"></div>
    
    <!-- 添加JavaScript函数 -->
    <script>
        function showPdfList() {
            fetch('/list_pdfs')
                .then(response => response.text())
                .then(html => {
                    document.getElementById('pdfList').innerHTML = html;
                })
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('pdfList').innerHTML = '获取文件列表失败';
                });
        }
    </script>
    
    <form method="POST" action="/download">
        <div class="form-group">
            <label for="jm_id">JM漫画ID:</label>
            <input type="text" id="jm_id" name="jm_id" placeholder="请输入JM漫画ID，例如：123456" required>
        </div>
        <div class="form-group">
            <label for="max_chapters">最大章节数:</label>
            <input type="number" id="max_chapters" name="max_chapters" placeholder="默认为1章" min="1" max="1000">
        </div>
        <button type="submit">开始下载</button>
    </form>
    
    <div class="status">
        <h2>下载任务状态</h2>
        {% if tasks %}
            {% for task_id, task in tasks.items() %}
                <div class="task {{ task.status }}">
                    <p><strong>JM ID:</strong> {{ task.jm_id }}</p>
                    <p><strong>状态:</strong> 
                        {% if task.status == 'completed' %}
                            已完成
                        {% elif task.status == 'in-progress' %}
                            下载中...
                        {% elif task.status == 'failed' %}
                            失败
                        {% endif %}
                    </p>
                    {% if task.message %}
                        <p><strong>消息:</strong> {{ task.message|safe }}</p>
                    {% endif %}
                    {% if task.pdf_url %}
                        <iframe src="{{ task.pdf_url }}" width="100%" height="600px"></iframe>
                    {% endif %}
                </div>
            {% endfor %}
        {% else %}
            <p>暂无下载任务</p>
        {% endif %}
    </div>
</body>
</html>
'''

# 存储下载任务状态
tasks = {}

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, tasks=tasks)

# 添加静态文件访问路由
# 修改 serve_pdf 函数中的路径
@app.route('/pdf/<path:filename>')
def serve_pdf(filename):
    try:
        pdf_dir = Path('E:\\tools\\image2pdf-main\\books\\pdf')
        print(f"请求的文件名: {filename}")
        
        # URL解码获取原始文件名
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        print(f"解码后的文件名: {decoded_filename}")
        
        # 首先尝试完全匹配
        exact_match = pdf_dir / decoded_filename
        if exact_match.exists():
            print(f"找到完全匹配的文件: {exact_match.name}")
            return send_from_directory(str(pdf_dir), exact_match.name, as_attachment=False)
            
        # 如果没有完全匹配，进行文件名标准化后比较
        def normalize_filename(name):
            # 保留更多的特殊字符，只移除系统不允许的字符
            allowed_chars = set('[]()（）{}【】「」『』《》、。，．!！?？ -_')
            return ''.join(c.lower() if c.isalnum() or c.isspace() or c in allowed_chars else ' ' for c in name)
        
        normalized_target = normalize_filename(decoded_filename)
        best_match = None
        best_ratio = 0
        
        # 列出目录中的所有文件用于调试
        print("目录中的所有PDF文件:")
        for file in pdf_dir.glob("*.pdf"):
            print(f"- {file.name}")
            normalized_file = normalize_filename(file.name)
            # 打印标准化后的文件名用于调试
            print(f"  标准化后: {normalized_file}")
            ratio = fuzz.ratio(normalized_target, normalized_file)
            print(f"  相似度: {ratio}")
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = file
        
        if best_match and best_ratio >= 70:  # 降低相似度阈值
            print(f"找到最相似的文件: {best_match.name}, 相似度: {best_ratio}")
            return send_from_directory(str(pdf_dir), best_match.name, as_attachment=False)
        else:
            raise FileNotFoundError(f"未找到相似的PDF文件: {filename}")
            
    except Exception as e:
        print(f"PDF访问错误: {str(e)}")
        return "PDF文件不存在或无法访问", 404

# 修改download_task函数中的PDF URL生成部分
def download_task(task_id, jm_id, max_chapters=None):
    try:
        tasks[task_id]['status'] = 'in-progress'
        tasks[task_id]['message'] = '正在下载中，请耐心等待...'
        
        # 加载配置文件
        option_file = os.path.join(os.path.dirname(__file__), 'config.yml')
        option = jmcomic.JmOption.from_file(option_file)
           
        # 确保JM号码格式正确
        if not jm_id.startswith('JM'):
            jm_id = f'JM{jm_id}'
        
        # 下载相册
        tasks[task_id]['message'] = f'正在下载 {jm_id}...'
        result = jmcomic.download_album(jm_id, option)
        album = result[0] if isinstance(result, tuple) else result 
        
        if album is None:
            raise Exception(f"JM下载失败: {jm_id}")
            
        # 使用相册标题作为文件名
        filename = DirRule.apply_rule_directly(album, None, "Atitle")
        pdf_path = f"{filename}.pdf"
        
        # 打印实际文件路径和名称以便调试
        actual_pdf_path = os.path.join('E:\\tools\\image2pdf-main\\books\\pdf', os.path.basename(pdf_path))
        print(f"实际PDF路径: {actual_pdf_path}")
        
            
        # URL编码文件名并更新任务状态
        encoded_filename = quote(os.path.basename(pdf_path))
        print(f"编码后的文件名: {encoded_filename}")
        pdf_url = f"/pdf/{encoded_filename}"
        tasks[task_id]['status'] = 'completed'
        tasks[task_id]['message'] = f'下载完成，<a href="{pdf_url}" target="_blank">点击查看PDF</a>'
        
        return pdf_path

    except Exception as e:
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['message'] = f'下载失败: {str(e)}'
        print(f"下载任务出错: {str(e)}")
        raise e

@app.route('/download', methods=['GET', 'POST'])
def download():
    if request.method == 'GET':
        # 处理 GET 请求，例如重定向到首页
        return redirect(url_for('index'))
    
    # 以下是原有的 POST 请求处理逻辑
    jm_id = request.form.get('jm_id')
    max_chapters = request.form.get('max_chapters')
    
    if not jm_id:
        return "请提供JM漫画ID", 400
    
    # 创建新任务
    # 使用UUID生成唯一任务ID
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        'jm_id': jm_id,
        'status': 'in-progress',
        'message': '初始化下载...'
    }
    
    # 在后台线程中执行下载任务
    thread = threading.Thread(target=download_task, args=(task_id, jm_id, max_chapters))
    thread.daemon = True
    thread.start()
    
    return redirect(url_for('index'))

# 添加新的路由来获取PDF文件列表
@app.route('/list_pdfs')
def list_pdfs():
    try:
        pdf_dir = Path('E:\\tools\\image2pdf-main\\books\\pdf')
        print(f"正在扫描目录: {pdf_dir}")
        
        # 检查目录是否存在
        if not pdf_dir.exists():
            print(f"目录不存在: {pdf_dir}")
            return "PDF目录不存在", 404
            
        files = []
        pdf_files = list(pdf_dir.glob("*.pdf"))
        print(f"找到 {len(pdf_files)} 个PDF文件")
        
        for file in pdf_files:
            print(f"处理文件: {file.name}")
            try:
                size = file.stat().st_size
                modified = file.stat().st_mtime
                files.append({
                    'name': file.name,
                    'size': f"{size / 1024 / 1024:.2f} MB",
                    'modified': datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S'),
                    'modified_timestamp': modified  # 添加时间戳用于排序
                })
            except Exception as e:
                print(f"处理文件 {file.name} 时出错: {str(e)}")
        
        # 按修改时间降序排序
        files.sort(key=lambda x: x['modified_timestamp'], reverse=True)
        
        if not files:
            return render_template_string('''
                <h2>PDF文件列表</h2>
                <p>目录为空或未找到PDF文件</p>
            ''')
            
        return render_template_string('''
            <h2>PDF文件列表</h2>
            <p>共找到 {{ files|length }} 个文件</p>
            <table style="width:100%; border-collapse: collapse;">
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">文件名</th>
                    <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">大小</th>
                    <th style="padding: 8px; text-align: left; border: 1px solid #ddd;">修改时间</th>
                </tr>
                {% for file in files %}
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">
                        <a href="/pdf/{{ file.name }}" target="_blank">{{ file.name }}</a>
                    </td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{{ file.size }}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{{ file.modified }}</td>
                </tr>
                {% endfor %}
            </table>
        ''', files=files)
    except Exception as e:
        print(f"获取文件列表时出错: {str(e)}")
        return f"获取文件列表失败: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)